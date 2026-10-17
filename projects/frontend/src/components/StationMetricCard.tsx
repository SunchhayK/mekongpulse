import type { FloodRiskTier, StationTelemetry } from "@/lib/api";
import { formatMeters, formatRate, TIER_META } from "@/lib/design";

export interface StationMetricCardProps {
  stationId: string;
  stationName: string;
  riverName: string;
  currentWaterLevelM: number;
  rateOfRiseMPerHour: number;
  alarmStageM: number;
  isStaleFallback?: boolean;
  floodStageM?: number;
  selected?: boolean;
  onSelect?: (stationId: string) => void;
}

export function stationTier(station: StationTelemetry, floodStage?: number): FloodRiskTier {
  const flood = floodStage ?? station.flood_stage_m;
  if (station.level_m >= flood) return "DANGER";
  if (station.level_m >= station.alarm_stage_m) return "WARNING";
  if (station.level_m >= station.alarm_stage_m - 2) return "ADVISORY";
  return "NORMAL";
}

export function StationMetricCard({
  stationId,
  stationName,
  riverName,
  currentWaterLevelM,
  rateOfRiseMPerHour,
  alarmStageM,
  isStaleFallback = false,
  floodStageM,
  selected = false,
  onSelect,
}: StationMetricCardProps) {
  const flood = floodStageM ?? alarmStageM + 2;
  const tier = stationTier(
    {
      station_id: stationId,
      name: stationName,
      river: riverName,
      level_m: currentWaterLevelM,
      alarm_stage_m: alarmStageM,
      flood_stage_m: flood,
      rate_of_rise_m_per_hr: rateOfRiseMPerHour,
      recorded_at: "",
      is_stale_fallback: isStaleFallback,
      source: "",
      staleness_minutes: null,
    },
    flood,
  );
  const fillPercent = Math.max(4, Math.min(100, (currentWaterLevelM / flood) * 100));
  const direction =
    rateOfRiseMPerHour > 0.005 ? "rising" : rateOfRiseMPerHour < -0.005 ? "falling" : "steady";
  const margin = alarmStageM - currentWaterLevelM;

  const content = (
    <>
      <div className="station-head">
        <div>
          <div className="title-medium">{stationName}</div>
          <div className="body-small muted">
            {riverName} · <span className="station-id">{stationId}</span>
          </div>
        </div>
        {isStaleFallback && (
          <span className="status-pill label-small" title="Estimated reading from station failover">
            ប៉ាន់ស្មាន · estimated
          </span>
        )}
      </div>
      <div className="level">
        <span className="value mono">{formatMeters(currentWaterLevelM)}</span>
        <span className="unit body-medium">m</span>
      </div>
      <div className="body-medium rate" data-direction={direction}>
        {direction === "rising" ? "▲" : direction === "falling" ? "▼" : "■"} {formatRate(rateOfRiseMPerHour)}
      </div>
      <div className="stage-track" aria-hidden="true">
        <div
          className="stage-fill"
          style={{ width: `${fillPercent}%`, background: TIER_META[tier].color }}
        />
        <span
          className="marker"
          style={{ left: `${Math.min(100, (alarmStageM / flood) * 100)}%` }}
          title={`Alarm stage ${formatMeters(alarmStageM)} m`}
        />
      </div>
      <div className="body-small muted">
        Alarm <span className="mono">{formatMeters(alarmStageM)}</span> · Flood{" "}
        <span className="mono">{formatMeters(flood)}</span> ·{" "}
        <span className="margin-badge">
          levee margin {margin > 0 ? "+" : ""}
          {margin.toFixed(2)} m
        </span>
      </div>
    </>
  );

  if (onSelect) {
    return (
      <button
        type="button"
        className="card station-card"
        aria-pressed={selected}
        onClick={() => onSelect(stationId)}
      >
        {content}
      </button>
    );
  }
  return <div className="card station-card">{content}</div>;
}
