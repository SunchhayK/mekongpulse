#!/usr/bin/env python3
"""Server-side benchmark: sync wall time, row writes, host and DB footprint.

Run on the host that runs the containers (stdlib only):

    cd ~/mekongpulse/projects
    set -a && . ./.env.staging && set +a
    python3 scripts/benchmark_server.py

It POSTs an admin endpoint (default /api/v1/telemetry/sync), waits for the
Postgres statistics collector to flush, and reports per-table row deltas.
Use `--endpoint /api/v1/patrol/run` to benchmark the cron path. The benchmark
performs a real sync: external MRC/weather calls and database writes.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

DB_CONTAINER = os.environ.get("DB_CONTAINER", "mekongpulse-server-db-1")
API_BASE = os.environ.get("API_BASE", "http://localhost:8080")

STATS_SQL = """
select relname, n_tup_ins, n_tup_upd
from pg_stat_user_tables
where schemaname = 'public'
order by relname;
"""
SIZE_SQL = """
select relname, pg_size_pretty(pg_total_relation_size(relid))
from pg_stat_user_tables
order by pg_total_relation_size(relid) desc
limit 8;
"""


def psql(sql: str) -> str:
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            DB_CONTAINER,
            "sh",
            "-c",
            'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -A -F"|" -f -',
        ],
        input=sql,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def table_stats() -> dict[str, tuple[int, int]]:
    rows = {}
    for line in psql(STATS_SQL).splitlines():
        relname, inserts, updates = line.split("|")
        rows[relname] = (int(inserts), int(updates))
    return rows


def wait_for_flush(before: dict[str, tuple[int, int]], timeout: float) -> dict[str, tuple[int, int]]:
    """Postgres may expose counter updates a few seconds after the write."""
    deadline = time.monotonic() + timeout
    latest = table_stats()
    while time.monotonic() < deadline:
        if any(latest[name] != values for name, values in before.items()):
            return latest
        time.sleep(1)
        latest = table_stats()
    return latest


def host_snapshot() -> list[str]:
    lines = []
    lines.append(f"- cores: {os.cpu_count()}")
    lines.append(f"- load: {', '.join(f'{v:.2f}' for v in os.getloadavg())}")
    free = subprocess.run(["free", "-m"], text=True, capture_output=True)
    if free.returncode == 0:
        mem = free.stdout.splitlines()[1].split()
        lines.append(f"- memory: {mem[2]} MiB used / {mem[1]} MiB total")
    usage = shutil.disk_usage("/")
    lines.append(f"- disk: {usage.used / 1e9:.0f} GB used / {usage.total / 1e9:.0f} GB")
    stats = subprocess.run(
        [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{.Name}} cpu={{.CPUPerc}} mem={{.MemUsage}}",
        ],
        text=True,
        capture_output=True,
    )
    for line in stats.stdout.splitlines():
        if "mekongpulse" in line:
            lines.append(f"- `{line}`")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="/api/v1/telemetry/sync")
    parser.add_argument("--stats-timeout", type=float, default=20.0)
    args = parser.parse_args()

    token = os.environ.get("ADMIN_TOKEN")
    if not token:
        print("ADMIN_TOKEN is not set. Source .env.staging first, for example:")
        print("  set -a && . ./.env.staging && set +a && python3 scripts/benchmark_server.py")
        return 1

    print(f"# Server benchmark\n\nendpoint: `{args.endpoint}`\n")
    before = table_stats()
    request = urllib.request.Request(
        API_BASE + args.endpoint,
        method="POST",
        headers={"Authorization": f"Bearer {token}"},
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=300) as response:
        body = json.loads(response.read())
    wall = time.perf_counter() - started
    after = wait_for_flush(before, args.stats_timeout)

    print(f"- wall: **{wall:.2f} s** · reported duration: {body.get('duration_ms')} ms")
    if body.get("communes_evaluated") is not None:
        print(
            f"- communes: {body.get('communes_evaluated')} evaluated, "
            f"{body.get('communes_skipped')} skipped · tiers: {body.get('risk_counts')}"
        )
    print("\n## Row deltas\n")
    print("| table | inserts | updates |")
    print("|---|---:|---:|")
    changed = False
    for name in sorted(before):
        ins = after[name][0] - before[name][0]
        upd = after[name][1] - before[name][1]
        if ins or upd:
            changed = True
            print(f"| `{name}` | {ins} | {upd} |")
    if not changed:
        print("| — | 0 | 0 |")
        print("\nNo row changes observed (expected when nothing changed).")

    print("\n## Host\n")
    print("\n".join(host_snapshot()))
    print("\n## Largest tables\n")
    print("| table | size |")
    print("|---|---:|")
    for line in psql(SIZE_SQL).splitlines():
        name, size = line.split("|")
        print(f"| `{name}` | {size} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
