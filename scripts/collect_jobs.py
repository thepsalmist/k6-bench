"""Export job timings after a run and summarise queue latency per scenario step.

The job table must have: job_id, status, enqueued_at, started_at, finished_at,
with timestamps as epoch seconds.
"""

import argparse
import bisect
import csv
import gzip
import json
import math
import time
from pathlib import Path

import psycopg
from psycopg import sql


def pct(sorted_values: list[float], q: float) -> float | None:
    if not sorted_values:
        return None
    rank = max(0, math.ceil(q * len(sorted_values)) - 1)
    return sorted_values[rank]


def drain(conn: psycopg.Connection, table: str, timeout: float) -> int:
    query = sql.SQL("SELECT count(*) FROM {} WHERE finished_at IS NULL").format(sql.Identifier(table))
    deadline = time.time() + timeout
    while True:
        pending = conn.execute(query).fetchone()[0]
        if pending == 0 or time.time() >= deadline:
            return pending
        print(f"collect_jobs: waiting for {pending} unfinished jobs", flush=True)
        time.sleep(5)


def summarise(rows: list[dict], schedule: dict) -> list[dict]:
    start = schedule["start_epoch_ms"] / 1000
    out = []
    for seg in schedule["segments"]:
        lo, hi = start + seg["start"], start + seg["end"]
        jobs = [r for r in rows if lo <= r["enqueued_at"] < hi]
        started = [r for r in jobs if r["started_at"] is not None]
        wait = sorted((r["started_at"] - r["enqueued_at"]) * 1000 for r in started)
        run = sorted((r["finished_at"] - r["started_at"]) * 1000 for r in started)
        out.append(
            {
                "phase": seg["phase"],
                "step": seg["step"],
                "target_rate": seg["rate"],
                "seconds": seg["end"] - seg["start"],
                "enqueued": len(jobs),
                "enqueued_per_s": len(jobs) / (seg["end"] - seg["start"]),
                "not_started": len(jobs) - len(started),
                "queue_ms_p50": pct(wait, 0.50),
                "queue_ms_p95": pct(wait, 0.95),
                "queue_ms_p99": pct(wait, 0.99),
                "queue_ms_max": wait[-1] if wait else None,
                "run_ms_p50": pct(run, 0.50),
                "run_ms_p95": pct(run, 0.95),
            }
        )
    return out


def backlog(rows: list[dict], schedule: dict, out: Path) -> None:
    start = schedule["start_epoch_ms"] / 1000
    enq = sorted(r["enqueued_at"] for r in rows)
    sta = sorted(r["started_at"] for r in rows if r["started_at"] is not None)
    end = max([schedule["end_epoch_ms"] / 1000, *(enq[-1:]), *(sta[-1:])])
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "enqueued_total", "started_total", "backlog"])
        for t in range(math.ceil(end - start) + 1):
            e = bisect.bisect_right(enq, start + t)
            s = bisect.bisect_right(sta, start + t)
            w.writerow([t, e, s, e - s])


def fmt(v: float | None) -> str:
    return "-" if v is None else f"{v:.1f}"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dsn", required=True)
    p.add_argument("--table", required=True)
    p.add_argument("--schedule", type=Path, required=True)
    p.add_argument("--drain-timeout", type=float, default=300)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()

    schedule = json.loads(a.schedule.read_text())
    with psycopg.connect(a.dsn, autocommit=True) as conn:
        drain_started = time.time()
        pending = drain(conn, a.table, a.drain_timeout)
        drain_seconds = time.time() - drain_started
        cur = conn.cursor(row_factory=psycopg.rows.dict_row)
        rows = cur.execute(
            sql.SQL(
                "SELECT job_id::text, status, enqueued_at, started_at, finished_at FROM {} ORDER BY enqueued_at"
            ).format(sql.Identifier(a.table))
        ).fetchall()

    with gzip.open(a.out / "jobs.csv.gz", "wt", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["job_id", "status", "enqueued_at", "started_at", "finished_at"])
        w.writeheader()
        w.writerows(rows)
    backlog(rows, schedule, a.out / "backlog.csv")

    steps = summarise(rows, schedule)
    summary = {
        "total_jobs": len(rows),
        "unfinished_after_drain": pending,
        "drain_seconds": round(drain_seconds, 1),
        "steps": steps,
    }
    (a.out / "jobs_summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    print(f"\njobs: {len(rows)} total, {pending} unfinished after {drain_seconds:.0f}s drain")
    heads = ["step", "jobs/s", "jobs", "unstarted", "queue p50", "queue p95", "queue p99", "run p50"]
    print(" ".join(f"{h:>10}" for h in heads))
    for s in steps:
        if s["phase"] != "hold":
            continue
        cells = [s["step"], f"{s['enqueued_per_s']:.1f}", s["enqueued"], s["not_started"]]
        cells += [fmt(s[k]) for k in ("queue_ms_p50", "queue_ms_p95", "queue_ms_p99", "run_ms_p50")]
        print(" ".join(f"{c:>10}" for c in cells))
    print("(times in ms)")


if __name__ == "__main__":
    main()
