#!/usr/bin/env python3
"""Benchmark the public MekongPulse API.

Stdlib only. Measures median/min latency and transferred size over a real
network path; `--assess` additionally measures a cold vs cached voice bulletin
(it may consume one Gemini TTS call, so it is opt-in).

Examples:
    python3 scripts/benchmark_api.py
    python3 scripts/benchmark_api.py --base-url http://localhost:8080 --runs 5
    python3 scripts/benchmark_api.py --assess 030101
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request

DEFAULT_BASE = "https://mekongpulse-api.labyrinth.buzz"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0 Safari/537.36"
)
ENDPOINTS = [
    "/health",
    "/telemetry/latest",
    "/communes/risk-map",
    "/communes/030101",
    "/communes/030101/evidence",
    "/communes/030101/reports",
]


def request(url: str, *, gzip: bool = True, payload: dict | None = None):
    headers = {"User-Agent": USER_AGENT}
    if gzip:
        headers["Accept-Encoding"] = "gzip"
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        url, data=data, headers=headers, method="POST" if payload is not None else "GET"
    )
    started = time.perf_counter()
    with urllib.request.urlopen(req, timeout=240) as response:
        body = response.read()
        status = response.status
    return time.perf_counter() - started, len(body), status, body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument(
        "--assess",
        metavar="COMMUNE",
        help="also time POST /communes/{code}/assess twice (cold TTS + cached)",
    )
    args = parser.parse_args()
    base = args.base_url.rstrip("/") + "/api/v1"

    print(f"# API benchmark\n\nbase: `{base}` · runs: {args.runs}\n")
    print("| endpoint | median | min | transferred | raw |")
    print("|---|---:|---:|---:|---:|")
    for path in ENDPOINTS:
        try:
            samples = [request(base + path) for _ in range(args.runs)]
            raw = request(base + path, gzip=False)[1]
            times = [s[0] for s in samples]
            print(
                f"| `{path}` | {statistics.median(times) * 1000:.0f} ms | "
                f"{min(times) * 1000:.0f} ms | {samples[-1][1] / 1024:.1f} KiB | "
                f"{raw / 1024:.1f} KiB |"
            )
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"| `{path}` | error | — | — | — |  ({exc})")

    if args.assess:
        print("\n## Voice assessment (cold vs cached)\n")
        results = []
        for attempt in (1, 2):
            started = time.perf_counter()
            req = urllib.request.Request(
                f"{base}/communes/{args.assess}/assess",
                data=json.dumps({"with_audio": True}).encode(),
                headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=240) as response:
                body = json.loads(response.read())
            elapsed = time.perf_counter() - started
            audio = body.get("audio") or {}
            results.append((elapsed, audio.get("url")))
            label = "cold" if attempt == 1 else "cached"
            print(
                f"- **{label}**: {elapsed * 1000:.0f} ms · tier {body.get('risk_tier')} · "
                f"`{audio.get('url') or 'no audio'}`"
            )
        if len(results) == 2 and results[0][1] == results[1][1]:
            print(f"- reuse speedup: **{results[0][0] / results[1][0]:.1f}×**")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
