#!/usr/bin/env python3
"""Google Earth Engine Sentinel-1 SAR flood-extent verification for MekongPulse.

Cross-checks lowland commune DANGER alerts and ground-truth field reports
against Sentinel-1 GRD (VV/VH backscatter) radar inundation masks to verify
whether surface water expanded compared to a dry-season baseline.

Usage:
    python projects/analytics/gee_sar_verify.py \
        --commune-code 080404 --lat 11.15 --lng 105.05 \
        --event-date 2026-10-15 --buffer-m 3000

Requires:
    pip install earthengine-api
    earthengine authenticate  (or GOOGLE_APPLICATION_CREDENTIALS / Workload Identity)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any

# Backscatter change threshold (dB) indicating newly inundated surface water in
# Sentinel-1 VH polarization over Mekong floodplains (specular reflection drops).
DEFAULT_VH_DROP_DB = -3.0
DEFAULT_WATER_VH_DB = -20.0
DEFAULT_FLOOD_FRACTION_THRESHOLD = 0.08


@dataclass(frozen=True)
class SarVerificationResult:
    commune_code: str
    event_date: str
    buffer_m: int
    flooded_area_ha: float
    total_area_ha: float
    flood_fraction: float
    inundation_detected: bool
    baseline_images: int
    event_images: int
    source: str = "sentinel1_sar_gee"


def verify_commune_sar(
    *,
    commune_code: str,
    lat: float,
    lng: float,
    event_date: date,
    buffer_m: int = 3000,
    event_window_days: int = 6,
    baseline_days: int = 60,
    vh_drop_db: float = DEFAULT_VH_DROP_DB,
    water_vh_db: float = DEFAULT_WATER_VH_DB,
    flood_fraction_threshold: float = DEFAULT_FLOOD_FRACTION_THRESHOLD,
    ee_module: Any | None = None,
) -> SarVerificationResult:
    """Compute Sentinel-1 SAR inundation fraction around a commune centroid."""
    ee = ee_module
    if ee is None:
        try:
            import ee as _ee  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "earthengine-api is required. Install with: pip install earthengine-api"
            ) from exc
        ee = _ee
        ee.Initialize()

    roi = ee.Geometry.Point([lng, lat]).buffer(buffer_m)

    event_start = (event_date - timedelta(days=event_window_days)).isoformat()
    event_end = (event_date + timedelta(days=event_window_days)).isoformat()
    # Pre-monsoon dry reference window (February-April of the same year)
    baseline_start = date(event_date.year, 2, 1).isoformat()
    baseline_end = (date(event_date.year, 2, 1) + timedelta(days=baseline_days)).isoformat()

    collection = (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filterBounds(roi)
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
        .select("VH")
    )

    baseline_col = collection.filterDate(baseline_start, baseline_end)
    event_col = collection.filterDate(event_start, event_end)

    baseline_count = int(baseline_col.size().getInfo())
    event_count = int(event_col.size().getInfo())
    if baseline_count == 0 or event_count == 0:
        return SarVerificationResult(
            commune_code=commune_code,
            event_date=event_date.isoformat(),
            buffer_m=buffer_m,
            flooded_area_ha=0.0,
            total_area_ha=round((3.14159265 * (buffer_m**2)) / 10_000.0, 2),
            flood_fraction=0.0,
            inundation_detected=False,
            baseline_images=baseline_count,
            event_images=event_count,
        )

    baseline_img = baseline_col.median().clip(roi)
    event_img = event_col.min().clip(roi)
    diff_img = event_img.subtract(baseline_img)

    # Pixel is flagged as newly inundated if VH dropped below threshold AND
    # absolute event VH indicates smooth water surface.
    flood_mask = diff_img.lt(vh_drop_db).And(event_img.lt(water_vh_db))
    pixel_area_ha = ee.Image.pixelArea().divide(10_000.0)

    flooded_stats = (
        pixel_area_ha.updateMask(flood_mask)
        .reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=roi,
            scale=20,
            maxPixels=1e8,
        )
        .getInfo()
    )
    total_stats = (
        pixel_area_ha.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=roi,
            scale=20,
            maxPixels=1e8,
        )
        .getInfo()
    )

    flooded_ha = float(flooded_stats.get("area", 0.0) or 0.0)
    total_ha = float(total_stats.get("area", 1.0) or 1.0)
    fraction = round(min(1.0, max(0.0, flooded_ha / total_ha)), 4)

    return SarVerificationResult(
        commune_code=commune_code,
        event_date=event_date.isoformat(),
        buffer_m=buffer_m,
        flooded_area_ha=round(flooded_ha, 2),
        total_area_ha=round(total_ha, 2),
        flood_fraction=fraction,
        inundation_detected=fraction >= flood_fraction_threshold,
        baseline_images=baseline_count,
        event_images=event_count,
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify MekongPulse commune flood alerts using Sentinel-1 SAR in Google Earth Engine."
    )
    parser.add_argument("--commune-code", required=True, help="6-digit MEF commune code")
    parser.add_argument("--lat", type=float, required=True, help="Commune latitude (WGS84)")
    parser.add_argument("--lng", type=float, required=True, help="Commune longitude (WGS84)")
    parser.add_argument(
        "--event-date",
        default=date.today().isoformat(),
        help="ISO date (YYYY-MM-DD) of the flood alert or field report",
    )
    parser.add_argument("--buffer-m", type=int, default=3000, help="Analysis radius in meters")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    result = verify_commune_sar(
        commune_code=args.commune_code,
        lat=args.lat,
        lng=args.lng,
        event_date=date.fromisoformat(args.event_date),
        buffer_m=args.buffer_m,
    )
    print(json.dumps(asdict(result), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
