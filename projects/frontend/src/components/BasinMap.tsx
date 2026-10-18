"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import type {
  Canvas,
  CircleMarkerOptions,
  LayerGroup,
  Map as LeafletMap,
  TileLayer,
} from "leaflet";
import type { CommuneRiskRow, StationTelemetry } from "@/lib/api";
import { formatMeters, KH_BBOX, TIER_META, TIER_ORDER } from "@/lib/design";
import "leaflet/dist/leaflet.css";
import "./basin-map.css";

export interface BasinMapProps {
  communes: CommuneRiskRow[];
  stations: StationTelemetry[];
  selectedStationId?: string;
  onSelectCommune: (communeCode: string) => void;
  onSelectStation?: (stationId: string) => void;
}

type BasemapStyle = "light" | "streets" | "terrain";
type LeafletModule = typeof import("leaflet");
type PositionedCommune = CommuneRiskRow & { lat: number; lng: number };

const BASEMAPS: Record<
  BasemapStyle,
  { labelKey: "basemapLight" | "basemapStreets" | "basemapTerrain"; url: string; attribution: string }
> = {
  light: {
    labelKey: "basemapLight",
    // CARTO's keyless Positron endpoint now serves watermarked
    // "API KEY REQUIRED" tiles; Esri's light-gray canvas stays keyless.
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    attribution:
      "Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors",
  },
  streets: {
    labelKey: "basemapStreets",
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: "&copy; OpenStreetMap contributors",
  },
  terrain: {
    labelKey: "basemapTerrain",
    url: "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
    attribution: "&copy; OpenStreetMap contributors, SRTM | &copy; OpenTopoMap (CC-BY-SA)",
  },
};

const BASEMAP_ORDER: BasemapStyle[] = ["light", "streets", "terrain"];

const KH_CENTER: [number, number] = [
  (KH_BBOX.minLat + KH_BBOX.maxLat) / 2,
  (KH_BBOX.minLng + KH_BBOX.maxLng) / 2,
];

// TIER_META colours are CSS custom properties, which CanvasRenderingContext2D
// cannot parse. Resolve them once per rebuild before handing them to Leaflet.
function cssColor(value: string): string {
  if (!value.startsWith("var(")) return value;
  const property = value.slice(4, -1).trim();
  return getComputedStyle(document.documentElement).getPropertyValue(property).trim() || value;
}

export function BasinMap({
  communes,
  stations,
  selectedStationId,
  onSelectCommune,
  onSelectStation,
}: BasinMapProps) {
  const t = useTranslations("Map");
  const tierT = useTranslations("Tier");
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const leafletRef = useRef<LeafletModule | null>(null);
  const tileRef = useRef<TileLayer | null>(null);
  const markerGroupRef = useRef<LayerGroup | null>(null);
  const rendererRef = useRef<Canvas | null>(null);
  const fittedRef = useRef(false);
  const handlersRef = useRef({ onSelectCommune, onSelectStation });
  const [mapEpoch, setMapEpoch] = useState(0);
  const [basemap, setBasemap] = useState<BasemapStyle>("light");

  const positioned = useMemo(
    () => communes.filter((row): row is PositionedCommune => row.lat != null && row.lng != null),
    [communes],
  );

  // Keep click handlers current without rebuilding markers on every parent render.
  useEffect(() => {
    handlersRef.current = { onSelectCommune, onSelectStation };
  }, [onSelectCommune, onSelectStation]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || mapRef.current) return;
    let disposed = false;
    let map: LeafletMap | null = null;

    void (async () => {
      const L = await import("leaflet");
      if (disposed || mapRef.current) return;
      leafletRef.current = L;

      map = L.map(container, {
        center: KH_CENTER,
        zoom: 7,
        minZoom: 5,
        maxZoom: 17,
        zoomControl: false,
        scrollWheelZoom: false,
        attributionControl: true,
      });
      L.control.zoom({
        position: "bottomright",
        zoomInTitle: t("zoomIn"),
        zoomOutTitle: t("zoomOut"),
      }).addTo(map);
      rendererRef.current = L.canvas({ padding: 0.5 }).addTo(map);
      markerGroupRef.current = L.layerGroup().addTo(map);
      mapRef.current = map;
      setMapEpoch((epoch) => epoch + 1);
    })();

    return () => {
      disposed = true;
      map?.remove();
      map = null;
      mapRef.current = null;
      leafletRef.current = null;
      tileRef.current = null;
      markerGroupRef.current = null;
      rendererRef.current = null;
      fittedRef.current = false;
    };
  }, [t]);

  // Swap the raster basemap in place; Leaflet's attribution control follows
  // the layer add/remove events, so the credits change with the tiles.
  useEffect(() => {
    const L = leafletRef.current;
    const map = mapRef.current;
    if (!mapEpoch || !L || !map) return;
    const style = BASEMAPS[basemap];
    tileRef.current?.remove();
    tileRef.current = L.tileLayer(style.url, {
      attribution: style.attribution,
      maxZoom: 17,
    }).addTo(map);
  }, [mapEpoch, basemap]);

  useEffect(() => {
    const L = leafletRef.current;
    const map = mapRef.current;
    const group = markerGroupRef.current;
    const renderer = rendererRef.current;
    if (!mapEpoch || !L || !map || !group || !renderer) return;

    group.clearLayers();

    const colors = new Map<string, string>();
    const colorOf = (value: string) => {
      const cached = colors.get(value);
      if (cached) return cached;
      const resolved = cssColor(value);
      colors.set(value, resolved);
      return resolved;
    };
    const paper = colorOf("var(--paper)");

    positioned.forEach((row) => {
      if (row.tier === "NORMAL") {
        L.circleMarker([row.lat, row.lng], {
          renderer,
          radius: 2.5,
          stroke: false,
          fillColor: colorOf(TIER_META.NORMAL.color),
          fillOpacity: 0.35,
          opacity: 0.35,
          interactive: false,
        }).addTo(group);
        return;
      }

      const meta = TIER_META[row.tier];
      const lead =
        row.lead_time_hours != null ? t("floodArrival", { hours: row.lead_time_hours }) : "";
      const options: CircleMarkerOptions & { keyboard: boolean } = {
        renderer,
        radius: 5,
        fillColor: colorOf(meta.color),
        fillOpacity: 1,
        color: paper,
        weight: 1.5,
        opacity: 1,
        interactive: true,
        keyboard: true,
        bubblingMouseEvents: false,
      };
      const marker = L.circleMarker([row.lat, row.lng], options);
      marker.bindTooltip(
        `${row.commune_name_kh} · ${row.commune_name_en} - ${tierT(row.tier)}${lead}`,
        { direction: "top", offset: [0, -6], opacity: 1, className: "basin-tooltip" },
      );
      marker.on("click", () => handlersRef.current.onSelectCommune(row.commune_code));
      marker.addTo(group);
    });

    stations.forEach((station) => {
      const position = STATION_POSITIONS[station.station_id];
      if (!position) return;
      const selected = station.station_id === selectedStationId;
      const level = formatMeters(station.level_m);
      const stationLabel = t("stationTooltip", { name: station.name, level });
      const marker = L.marker([position.lat, position.lng], {
        icon: L.divIcon({
          className: `basin-station-icon${selected ? " is-selected" : ""}`,
          html: '<span class="basin-station-diamond"></span>',
          iconSize: [18, 18],
          iconAnchor: [9, 9],
          tooltipAnchor: [0, -12],
        }),
        keyboard: true,
        title: stationLabel,
        riseOnHover: true,
      });
      marker.bindTooltip(stationLabel, {
        direction: "top",
        opacity: 1,
        className: "basin-tooltip",
      });
      marker.on("click", () => handlersRef.current.onSelectStation?.(station.station_id));
      marker.addTo(group);
    });

    if (!fittedRef.current && positioned.length > 0) {
      map.fitBounds(
        L.latLngBounds(positioned.map((row) => [row.lat, row.lng] as [number, number])),
        { padding: [28, 28], maxZoom: 9 },
      );
      fittedRef.current = true;
    }
  }, [mapEpoch, positioned, stations, selectedStationId, t, tierT]);

  return (
    <div className="map-shell">
      <div className="basin-map-frame">
        <div
          ref={containerRef}
          className="basin-map-canvas"
          role="region"
          aria-label={t("aria", { count: positioned.length })}
        />
        <div className="basemap-switcher" role="group" aria-label={t("basemapAria")}>
          {BASEMAP_ORDER.map((style) => (
            <button
              key={style}
              type="button"
              className="basemap-option label-small"
              aria-pressed={basemap === style}
              onClick={() => setBasemap(style)}
            >
              {t(BASEMAPS[style].labelKey)}
            </button>
          ))}
        </div>
      </div>
      <div className="map-legend label-small">
        {TIER_ORDER.map((tier) => (
          <span className="item" key={tier}>
            <span className="swatch" style={{ background: TIER_META[tier].color }} />
            {tierT(tier)}
          </span>
        ))}
        <span className="item">
          <span className="station-mark" aria-hidden="true" /> {t("stationLegend")}
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
