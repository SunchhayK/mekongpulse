"use client";

import type { CommuneRiskRow, StationTelemetry } from "@/lib/api";
import { formatMeters, project, TIER_META, TIER_ORDER } from "@/lib/design";

export interface BasinMapProps {
  communes: CommuneRiskRow[];
  stations: StationTelemetry[];
  selectedStationId?: string;
  onSelectCommune: (communeCode: string) => void;
  onSelectStation?: (stationId: string) => void;
}

const WIDTH = 900;
const HEIGHT = 720;

export function BasinMap({
  communes,
  stations,
  selectedStationId,
  onSelectCommune,
  onSelectStation,
}: BasinMapProps) {
  const positioned = communes.filter(
    (row) => row.lat != null && row.lng != null,
  ) as (CommuneRiskRow & { lat: number; lng: number })[];

  return (
    <div className="map-shell">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="group"
        aria-label={`Cambodia basin map: ${positioned.length} monitored communes shaded by flood risk tier`}
      >
        {/* basin backdrop */}
        <rect width={WIDTH} height={HEIGHT} fill="var(--map-bg)" />
        {[...Array(7)].map((_, index) => (
          <line
            key={`grid-h-${index}`}
            x1={0}
            x2={WIDTH}
            y1={(HEIGHT / 7) * (index + 1)}
            y2={(HEIGHT / 7) * (index + 1)}
            stroke="var(--line)"
            strokeOpacity={0.8}
          />
        ))}
        {[...Array(9)].map((_, index) => (
          <line
            key={`grid-v-${index}`}
            x1={(WIDTH / 9) * (index + 1)}
            x2={(WIDTH / 9) * (index + 1)}
            y1={0}
            y2={HEIGHT}
            stroke="var(--line)"
            strokeOpacity={0.8}
          />
        ))}

        {/* baseline commune dots (decorative, no tab stops) */}
        {positioned
          .filter((row) => row.tier === "NORMAL")
          .map((row) => {
            const { x, y } = project(row.lat, row.lng, WIDTH, HEIGHT);
            return (
              <circle
                key={row.commune_code}
                cx={x}
                cy={y}
                r={2}
                fill="var(--tier-normal)"
                opacity={0.3}
                aria-hidden="true"
              />
            );
          })}

        {/* risk communes: focusable and selectable */}
        {positioned
          .filter((row) => row.tier !== "NORMAL")
          .map((row) => {
            const { x, y } = project(row.lat, row.lng, WIDTH, HEIGHT);
            const meta = TIER_META[row.tier];
            return (
              <circle
                key={row.commune_code}
                className="map-dot"
                cx={x}
                cy={y}
                r={5.5}
                fill={meta.color}
                stroke="var(--paper)"
                strokeWidth={1.5}
                role="button"
                tabIndex={0}
                aria-label={`${row.commune_name_en} (${row.commune_code}), ${row.commune_name_kh}, ${meta.labelEn} tier${
                  row.lead_time_hours != null ? `, flood arrival ~${row.lead_time_hours} hours` : ""
                }`}
                onClick={() => onSelectCommune(row.commune_code)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelectCommune(row.commune_code);
                  }
                }}
              >
                <title>
                  {row.commune_name_kh} · {row.commune_name_en} — {meta.labelEn}
                </title>
              </circle>
            );
          })}

        {/* monitoring stations */}
        {stations.map((station) => {
          const { x, y } = project(
            // station coordinates are not in the telemetry payload; place by
            // the roster geometry published in stations.json (fixed markers).
            STATION_POSITIONS[station.station_id]?.lat ?? 0,
            STATION_POSITIONS[station.station_id]?.lng ?? 0,
            WIDTH,
            HEIGHT,
          );
          const selected = station.station_id === selectedStationId;
          return (
            <g
              key={station.station_id}
              className="map-dot"
              role="button"
              tabIndex={0}
              aria-label={`Station ${station.name} (${station.station_id}), river level ${formatMeters(
                station.level_m,
              )} meters`}
              onClick={() => onSelectStation?.(station.station_id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelectStation?.(station.station_id);
                }
              }}
            >
              <rect
                x={x - 7}
                y={y - 7}
                width={14}
                height={14}
                transform={`rotate(45 ${x} ${y})`}
                fill={selected ? "var(--sky)" : "var(--navy)"}
                stroke="var(--paper)"
                strokeWidth={1.5}
              />
              <text
                x={x + 12}
                y={y + 4}
                fill="var(--ink)"
                fontSize={13}
                style={{ fontFamily: "var(--font-mono)" }}
              >
                {station.name} {station.level_m.toFixed(2)}m
              </text>
            </g>
          );
        })}
      </svg>
      <div className="map-legend label-small">
        {TIER_ORDER.map((tier) => (
          <span className="item" key={tier}>
            <span className="swatch" style={{ background: TIER_META[tier].color }} />
            {TIER_META[tier].labelKh} · {TIER_META[tier].labelEn}
          </span>
        ))}
        <span className="item">
          <span className="station-mark" aria-hidden="true" /> station / ស្ថានីយ
        </span>
      </div>
    </div>
  );
}

// Station geometry from projects/data/stations.json (verified 2026-10).
const STATION_POSITIONS: Record<string, { lat: number; lng: number }> = {
  "019802": { lat: 11.994647, lng: 105.46873 },
  "020102": { lat: 11.81117, lng: 104.80678 },
  "033401": { lat: 11.563, lng: 104.9353 },
  "033402": { lat: 11.242035, lng: 105.036156 },
};
