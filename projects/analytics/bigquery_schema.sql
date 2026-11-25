-- MekongPulse Analytical Warehouse Schema (BigQuery)
-- Dataset: `${PROJECT_ID}.mekongpulse_analytics`
-- Supports IMP-07: ground-truth verification and per-commune threshold calibration.

CREATE SCHEMA IF NOT EXISTS `mekongpulse_analytics`
OPTIONS (
  location = "asia-southeast1",
  description = "MekongPulse hydrological telemetry, alerts, field reports, and commune threshold calibrations"
);

CREATE TABLE IF NOT EXISTS `mekongpulse_analytics.hydro_observations` (
  station_id STRING NOT NULL,
  station_name STRING,
  river STRING,
  recorded_at TIMESTAMP NOT NULL,
  fetched_at TIMESTAMP NOT NULL,
  level_m FLOAT64 NOT NULL,
  rate_of_rise_m_per_hr FLOAT64,
  rain_mm FLOAT64,
  alarm_stage_m FLOAT64,
  flood_stage_m FLOAT64,
  is_stale_fallback BOOL NOT NULL,
  qc_status STRING,
  source STRING
)
PARTITION BY DATE(recorded_at)
CLUSTER BY station_id, recorded_at
OPTIONS (
  description = "15-minute MRC river gauge observations with QC status and observed rainfall"
);

CREATE TABLE IF NOT EXISTS `mekongpulse_analytics.weather_forecasts` (
  commune_code STRING NOT NULL,
  station_id STRING,
  issued_at TIMESTAMP NOT NULL,
  rain_24h_mm FLOAT64,
  rain_48h_mm FLOAT64,
  rain_72h_mm FLOAT64,
  flood_hub_tier STRING,
  flood_hub_lead_days INT64,
  flood_hub_discharge_m3s FLOAT64,
  source STRING
)
PARTITION BY DATE(issued_at)
CLUSTER BY commune_code, station_id
OPTIONS (
  description = "Open-Meteo precipitation and Google Flood Hub multi-day forecast snapshots"
);

CREATE TABLE IF NOT EXISTS `mekongpulse_analytics.sentinel_alerts` (
  alert_id STRING NOT NULL,
  patrol_run_id STRING,
  commune_code STRING NOT NULL,
  commune_name_en STRING,
  province STRING,
  station_id STRING,
  risk_tier STRING NOT NULL,
  score INT64,
  station_level_m FLOAT64,
  alarm_stage_m FLOAT64,
  flood_stage_m FLOAT64,
  predicted_lead_time_hours FLOAT64,
  levee_margin_m FLOAT64,
  recipients_count INT64,
  dispatched_at TIMESTAMP NOT NULL
)
PARTITION BY DATE(dispatched_at)
CLUSTER BY commune_code, risk_tier
OPTIONS (
  description = "Dispatched Sentinel flood alerts paired against field reports for precision/recall evaluation"
);

CREATE TABLE IF NOT EXISTS `mekongpulse_analytics.field_reports` (
  report_id STRING NOT NULL,
  commune_code STRING NOT NULL,
  status STRING NOT NULL, -- 'water_reached' | 'no_water' | 'other'
  note STRING,
  reporter_label STRING,
  source STRING,          -- 'telegram' | 'web' | 'gee_sar'
  sar_flood_fraction FLOAT64,
  reported_at TIMESTAMP NOT NULL
)
PARTITION BY DATE(reported_at)
CLUSTER BY commune_code, status
OPTIONS (
  description = "Ground-truth commune chief/farmer field reports and Sentinel-1 SAR inundation verifications"
);

CREATE TABLE IF NOT EXISTS `mekongpulse_analytics.commune_calibrations` (
  commune_code STRING NOT NULL,
  levee_margin_m FLOAT64 NOT NULL,
  lead_time_multiplier FLOAT64 NOT NULL,
  sample_size INT64 NOT NULL,
  precision_score FLOAT64,
  recall_score FLOAT64,
  mean_lead_time_error_hours FLOAT64,
  updated_at TIMESTAMP NOT NULL
)
CLUSTER BY commune_code
OPTIONS (
  description = "Calibrated per-commune levee_margin_m and arrival-time multipliers synced back to MekongPulse"
);
