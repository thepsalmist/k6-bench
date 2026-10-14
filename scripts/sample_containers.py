import argparse
import csv
import json
import re
import subprocess
import sys
import time
from pathlib import Path

UNITS = {"B": 1, "KB": 1e3, "MB": 1e6, "GB": 1e9, "KIB": 1024, "MIB": 1024**2, "GIB": 1024**3}


def to_bytes(text: str) -> float:
    m = re.fullmatch(r"([\d.]+)\s*([A-Za-z]+)", text.strip())
    return float(m.group(1)) * UNITS[m.group(2).upper()] if m else float("nan")


def sample(project: str) -> list[dict]:
    ids = subprocess.run(
        ["docker", "ps", "-q", "--filter", f"label=com.docker.compose.project={project}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    if not ids:
        return []
    out = subprocess.run(
        ["docker", "stats", "--no-stream", "--format", "{{json .}}", *ids],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    rows = []
    for line in out.splitlines():
        s = json.loads(line)
        used, limit = s["MemUsage"].split(" / ")
        rows.append(
            {
                "name": s["Name"],
                "cpu_pct": float(s["CPUPerc"].rstrip("%")),
                "mem_bytes": to_bytes(used),
                "mem_limit_bytes": to_bytes(limit),
                "pids": s["PIDs"],
            }
        )
    return rows


def main() -> None:
    p = argparse.ArgumentParser(description="Sample docker stats for a compose project")
    p.add_argument("--project", required=True)
    p.add_argument("--interval", type=float, default=10)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()

    fields = ["ts", "name", "cpu_pct", "mem_bytes", "mem_limit_bytes", "pids"]
    with a.out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        while True:
            started = time.time()
            try:
                for row in sample(a.project):
                    w.writerow({"ts": round(started, 3), **row})
                f.flush()
            except (subprocess.CalledProcessError, ValueError, KeyError) as exc:
                print(f"sample_containers: {exc}", file=sys.stderr, flush=True)
            time.sleep(max(0.0, a.interval - (time.time() - started)))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
