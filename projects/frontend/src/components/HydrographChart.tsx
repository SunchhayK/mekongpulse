"use client";

import { useEffect, useMemo, useRef, useState } from "react";

export interface HydroObservation {
  timestamp: string; // ISO 8601
  waterLevelMeters: number;
  rainfallMm?: number;
  temperatureC?: number;
}

export interface HydrographChartProps {
  /** Station identifier (e.g. "020102") */
  stationId: string;
  /** Human-readable station name (e.g. "Prek Kdam") */
  stationName: string;
  /** Official alarm elevation threshold in meters */
  alarmStageMeters: number;
  /** Official flood crest elevation threshold in meters */
  floodStageMeters: number;
  /** 7-day time series observations */
  observations: HydroObservation[];
}

const WIDTH = 960;
const HEIGHT = 420;
const PADDING = { left: 64, right: 56, top: 20, bottom: 36 };

function cssVar(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

export function HydrographChart({
  stationId,
  stationName,
  alarmStageMeters,
  floodStageMeters,
  observations,
}: HydrographChartProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const [hover, setHover] = useState<{ index: number; x: number; y: number } | null>(null);

  const sorted = useMemo(
    () =>
      [...observations].sort(
        (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
      ),
    [observations],
  );

  const trend = useMemo(() => {
    if (sorted.length < 2) return "no data";
    const delta = sorted[sorted.length - 1].waterLevelMeters - sorted[0].waterLevelMeters;
    if (delta > 0.05) return "rising";
    if (delta < -0.05) return "falling";
    return "steady";
  }, [sorted]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || sorted.length < 2) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = WIDTH * dpr;
    canvas.height = HEIGHT * dpr;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, WIDTH, HEIGHT);

    const primary = cssVar("--md-sys-color-primary", "#96ccff");
    const outlineVariant = cssVar("--md-sys-color-outline-variant", "#41474d");
    const onSurfaceVariant = cssVar("--md-sys-color-on-surface-variant", "#c1c7ce");
    const tertiary = cssVar("--md-sys-color-tertiary", "#f3c03f");
    const error = cssVar("--md-sys-color-error", "#ffb4ab");
    const surfaceLowest = cssVar("--md-sys-color-surface-container-lowest", "#0a0f14");

    const plotW = WIDTH - PADDING.left - PADDING.right;
    const plotH = HEIGHT - PADDING.top - PADDING.bottom;
    const times = sorted.map((point) => new Date(point.timestamp).getTime());
    const tMin = times[0];
    const tMax = times[times.length - 1];
    const levels = sorted.map((point) => point.waterLevelMeters);
    const yMin = Math.min(...levels, alarmStageMeters) - 0.4;
    const yMax = Math.max(...levels, floodStageMeters) + 0.4;

    const xOf = (time: number) =>
      PADDING.left + (tMax === tMin ? plotW / 2 : ((time - tMin) / (tMax - tMin)) * plotW);
    const yOf = (level: number) =>
      PADDING.top + plotH - ((level - yMin) / (yMax - yMin)) * plotH;

    // sunken plot canvas
    ctx.fillStyle = surfaceLowest;
    ctx.fillRect(PADDING.left, PADDING.top, plotW, plotH);

    // horizontal grid + y labels
    ctx.font = "12px 'Roboto Mono', monospace";
    ctx.fillStyle = onSurfaceVariant;
    ctx.strokeStyle = outlineVariant;
    ctx.lineWidth = 1;
    const ySteps = 5;
    for (let i = 0; i <= ySteps; i += 1) {
      const level = yMin + ((yMax - yMin) * i) / ySteps;
      const y = yOf(level);
      ctx.beginPath();
      ctx.moveTo(PADDING.left, y);
      ctx.lineTo(PADDING.left + plotW, y);
      ctx.stroke();
      ctx.textAlign = "right";
      ctx.textBaseline = "middle";
      ctx.fillText(level.toFixed(1), PADDING.left - 8, y);
    }

    // x labels (~5 ticks, day-ordered)
    const xSteps = 4;
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    for (let i = 0; i <= xSteps; i += 1) {
      const time = tMin + ((tMax - tMin) * i) / xSteps;
      const x = xOf(time);
      const label = new Intl.DateTimeFormat("en-GB", {
        timeZone: "Asia/Phnom_Penh",
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(new Date(time));
      ctx.fillText(label, x, PADDING.top + plotH + 8);
    }

    // threshold dashed lines
    const dashLine = (level: number, color: string, label: string) => {
      const y = yOf(Math.min(level, yMax));
      ctx.strokeStyle = color;
      ctx.setLineDash([6, 6]);
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(PADDING.left, y);
      ctx.lineTo(PADDING.left + plotW, y);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = color;
      ctx.textAlign = "left";
      ctx.textBaseline = "bottom";
      ctx.fillText(label, PADDING.left + 6, y - 4);
    };
    dashLine(alarmStageMeters, tertiary, `Alarm ${alarmStageMeters.toFixed(2)}m / កម្រិតប្រកាស`);
    dashLine(floodStageMeters, error, `Flood ${floodStageMeters.toFixed(2)}m / កម្រិតទឹកជំនន់`);

    // water level trajectory
    ctx.strokeStyle = primary;
    ctx.lineWidth = 2.5;
    ctx.lineJoin = "round";
    ctx.beginPath();
    sorted.forEach((point, index) => {
      const x = xOf(times[index]);
      const y = yOf(point.waterLevelMeters);
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // fill under the curve, flat low-opacity primary
    ctx.globalAlpha = 0.12;
    ctx.fillStyle = primary;
    ctx.beginPath();
    ctx.moveTo(xOf(times[0]), yOf(yMin));
    sorted.forEach((point, index) => ctx.lineTo(xOf(times[index]), yOf(point.waterLevelMeters)));
    ctx.lineTo(xOf(times[times.length - 1]), yOf(yMin));
    ctx.closePath();
    ctx.fill();
    ctx.globalAlpha = 1;

    // last point marker
    const lastX = xOf(times[times.length - 1]);
    const lastY = yOf(sorted[sorted.length - 1].waterLevelMeters);
    ctx.fillStyle = primary;
    ctx.beginPath();
    ctx.arc(lastX, lastY, 4, 0, Math.PI * 2);
    ctx.fill();

    // hover crosshair
    if (hover) {
      const point = sorted[hover.index];
      if (point) {
        const x = xOf(times[hover.index]);
        const y = yOf(point.waterLevelMeters);
        ctx.strokeStyle = outlineVariant;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, PADDING.top);
        ctx.lineTo(x, PADDING.top + plotH);
        ctx.stroke();
        ctx.strokeStyle = primary;
        ctx.beginPath();
        ctx.arc(x, y, 5, 0, Math.PI * 2);
        ctx.stroke();
      }
    }
  }, [sorted, alarmStageMeters, floodStageMeters, hover]);

  const current = sorted.length ? sorted[sorted.length - 1].waterLevelMeters : null;

  function handleMove(event: React.MouseEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap || sorted.length < 2) return;
    const rect = canvas.getBoundingClientRect();
    const scaleX = WIDTH / rect.width;
    const mouseX = (event.clientX - rect.left) * scaleX;
    // nearest sample by x distance
    const plotW = WIDTH - PADDING.left - PADDING.right;
    let best = 0;
    let bestDistance = Number.POSITIVE_INFINITY;
    sorted.forEach((point, index) => {
      const t = new Date(point.timestamp).getTime();
      const tMin = new Date(sorted[0].timestamp).getTime();
      const tMax = new Date(sorted[sorted.length - 1].timestamp).getTime();
      const x = PADDING.left + (tMax === tMin ? plotW / 2 : ((t - tMin) / (tMax - tMin)) * plotW);
      const distance = Math.abs(x - mouseX);
      if (distance < bestDistance) {
        bestDistance = distance;
        best = index;
      }
    });
    const point = sorted[best];
    const t = new Date(point.timestamp).getTime();
    const tMin = new Date(sorted[0].timestamp).getTime();
    const tMax = new Date(sorted[sorted.length - 1].timestamp).getTime();
    const xCanvas =
      PADDING.left + (tMax === tMin ? plotW / 2 : ((t - tMin) / (tMax - tMin)) * plotW);
    // canvas y for the point
    const levels = sorted.map((p) => p.waterLevelMeters);
    const yMin = Math.min(...levels, alarmStageMeters) - 0.4;
    const yMax = Math.max(...levels, floodStageMeters) + 0.4;
    const plotH = HEIGHT - PADDING.top - PADDING.bottom;
    const yCanvas =
      PADDING.top + plotH - ((point.waterLevelMeters - yMin) / (yMax - yMin)) * plotH;
    setHover({
      index: best,
      x: xCanvas * (rect.width / WIDTH),
      y: yCanvas * (rect.height / HEIGHT),
    });
  }

  if (sorted.length < 2) {
    return (
      <div className="empty-state body-medium" data-empty="true">
        Telemetry temporarily unavailable / ទិន្នន័យកម្ពស់ទឹកមិនទាន់មាន — run a telemetry sync and
        refresh.
      </div>
    );
  }

  const hoverPoint = hover ? sorted[hover.index] : null;

  return (
    <div className="hydrograph-canvas-wrap" ref={wrapRef}>
      <canvas
        ref={canvasRef}
        style={{ width: "100%", height: "auto", aspectRatio: `${WIDTH} / ${HEIGHT}` }}
        role="img"
        aria-label={`${stationName} (${stationId}) 7-day water level hydrograph. Current ${current?.toFixed(
          2,
        )} meters, ${trend}. Alarm stage ${alarmStageMeters.toFixed(2)} m, flood crest ${floodStageMeters.toFixed(
          2,
        )} m.`}
        onMouseMove={handleMove}
        onMouseLeave={() => setHover(null)}
      />
      {hoverPoint && hover && (
        <div className="hydrograph-tooltip label-small" style={{ left: hover.x, top: hover.y }}>
          {hoverPoint.waterLevelMeters.toFixed(2)} m · {new Date(hoverPoint.timestamp).toLocaleString("en-GB", {
            timeZone: "Asia/Phnom_Penh",
            day: "2-digit",
            month: "short",
            hour: "2-digit",
            minute: "2-digit",
          })}
        </div>
      )}
    </div>
  );
}
