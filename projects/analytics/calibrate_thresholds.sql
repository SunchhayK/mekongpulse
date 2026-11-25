-- MekongPulse Threshold & Lead-Time Calibration (BigQuery Scheduled Query + BigQuery ML)
-- Schedule: Weekly (Monday 02:00 Asia/Phnom_Penh)
-- Pairs dispatched sentinel alerts with ground-truth field reports (+/- 24h)
-- to evaluate precision/recall and calibrate per-commune levee_margin_m and
-- flood-arrival lead_time_multiplier.

-- 1. Build paired training/evaluation table from the last 180 days.
CREATE OR REPLACE TABLE `mekongpulse_analytics.paired_alert_outcomes` AS
WITH alerts AS (
  SELECT
    alert_id,
    commune_code,
    station_id,
    risk_tier,
    station_level_m,
    alarm_stage_m,
    flood_stage_m,
    predicted_lead_time_hours,
    COALESCE(levee_margin_m, 0.30) AS used_levee_margin_m,
    dispatched_at
  FROM `mekongpulse_analytics.sentinel_alerts`
  WHERE dispatched_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 180 DAY)
    AND risk_tier IN ('WARNING', 'DANGER')
),
reports AS (
  SELECT
    report_id,
    commune_code,
    status,
    sar_flood_fraction,
    reported_at
  FROM `mekongpulse_analytics.field_reports`
  WHERE reported_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 180 DAY)
    AND status IN ('water_reached', 'no_water')
)
SELECT
  a.alert_id,
  a.commune_code,
  a.station_id,
  a.risk_tier,
  a.station_level_m,
  a.alarm_stage_m,
  a.flood_stage_m,
  a.station_level_m - a.alarm_stage_m AS level_above_alarm_m,
  a.predicted_lead_time_hours,
  a.used_levee_margin_m,
  a.dispatched_at,
  r.report_id,
  r.status AS ground_truth_status,
  r.reported_at,
  TIMESTAMP_DIFF(r.reported_at, a.dispatched_at, MINUTE) / 60.0 AS actual_lead_time_hours,
  CASE WHEN r.status = 'water_reached' THEN 1.0 ELSE 0.0 END AS flooded_label
FROM alerts a
JOIN reports r
  ON a.commune_code = r.commune_code
 AND r.reported_at BETWEEN TIMESTAMP_SUB(a.dispatched_at, INTERVAL 6 HOUR)
                       AND TIMESTAMP_ADD(a.dispatched_at, INTERVAL 24 HOUR);

-- 2. Train BigQuery ML linear regression model to predict arrival lead-time ratio
--    from station excess above alarm stage and commune identity.
CREATE OR REPLACE MODEL `mekongpulse_analytics.lead_time_calibration_model`
OPTIONS (
  model_type = 'LINEAR_REG',
  input_label_cols = ['lead_time_ratio'],
  l2_reg = 0.1
) AS
SELECT
  commune_code,
  station_id,
  level_above_alarm_m,
  SAFE_DIVIDE(
    GREATEST(actual_lead_time_hours, 1.0),
    GREATEST(predicted_lead_time_hours, 1.0)
  ) AS lead_time_ratio
FROM `mekongpulse_analytics.paired_alert_outcomes`
WHERE ground_truth_status = 'water_reached'
  AND predicted_lead_time_hours IS NOT NULL
  AND predicted_lead_time_hours > 0
  AND actual_lead_time_hours > 0;

-- 3. Merge calibrated per-commune levee_margin_m and lead_time_multiplier
--    (bounded to safe hydrological ranges: margin [0.10m, 0.80m], multiplier [0.5, 2.0]).
MERGE `mekongpulse_analytics.commune_calibrations` AS target
USING (
  WITH per_commune AS (
    SELECT
      commune_code,
      COUNT(*) AS sample_size,
      COUNTIF(ground_truth_status = 'water_reached') AS tp,
      COUNTIF(ground_truth_status = 'no_water') AS fp,
      AVG(
        CASE
          WHEN ground_truth_status = 'water_reached' AND predicted_lead_time_hours > 0
          THEN ABS(actual_lead_time_hours - predicted_lead_time_hours)
        END
      ) AS mean_lead_time_error_hours,
      AVG(
        CASE
          WHEN ground_truth_status = 'water_reached' AND predicted_lead_time_hours > 0 AND actual_lead_time_hours > 0
          THEN actual_lead_time_hours / predicted_lead_time_hours
        END
      ) AS empirical_ratio,
      AVG(used_levee_margin_m) AS avg_used_margin
    FROM `mekongpulse_analytics.paired_alert_outcomes`
    GROUP BY commune_code
    HAVING COUNT(*) >= 3
  )
  SELECT
    commune_code,
    -- If false-positive rate is high (precision < 0.6), tighten margin downward;
    -- if flooding occurs early (precision >= 0.85), widen safety margin conservatively.
    LEAST(0.80, GREATEST(0.10,
      avg_used_margin + CASE
        WHEN SAFE_DIVIDE(tp, tp + fp) < 0.60 THEN -0.05
        WHEN SAFE_DIVIDE(tp, tp + fp) >= 0.85 THEN 0.05
        ELSE 0.0
      END
    )) AS levee_margin_m,
    LEAST(2.0, GREATEST(0.5, COALESCE(empirical_ratio, 1.0))) AS lead_time_multiplier,
    sample_size,
    SAFE_DIVIDE(tp, tp + fp) AS precision_score,
    CAST(NULL AS FLOAT64) AS recall_score,
    mean_lead_time_error_hours,
    CURRENT_TIMESTAMP() AS updated_at
  FROM per_commune
) AS src
ON target.commune_code = src.commune_code
WHEN MATCHED THEN
  UPDATE SET
    levee_margin_m = src.levee_margin_m,
    lead_time_multiplier = src.lead_time_multiplier,
    sample_size = src.sample_size,
    precision_score = src.precision_score,
    mean_lead_time_error_hours = src.mean_lead_time_error_hours,
    updated_at = src.updated_at
WHEN NOT MATCHED THEN
  INSERT (
    commune_code,
    levee_margin_m,
    lead_time_multiplier,
    sample_size,
    precision_score,
    recall_score,
    mean_lead_time_error_hours,
    updated_at
  )
  VALUES (
    src.commune_code,
    src.levee_margin_m,
    src.lead_time_multiplier,
    src.sample_size,
    src.precision_score,
    src.recall_score,
    src.mean_lead_time_error_hours,
    src.updated_at
  );
