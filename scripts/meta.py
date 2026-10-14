import argparse
import json
import os
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path


def run(*cmd: str) -> str | None:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def git_info(root: Path) -> dict:
    commit = run("git", "-C", str(root), "rev-parse", "HEAD")
    status = run("git", "-C", str(root), "status", "--porcelain")
    return {"commit": commit, "dirty": bool(status) if status is not None else None}


def containers() -> list[dict]:
    ids = (run("docker", "compose", "ps", "-aq") or "").split()
    out = []
    for info in json.loads(run("docker", "inspect", *ids) or "[]") if ids else []:
        image = json.loads(run("docker", "image", "inspect", info["Image"]) or "[{}]")[0]
        host = info["HostConfig"]
        out.append(
            {
                "service": info["Config"]["Labels"].get("com.docker.compose.service"),
                "image": info["Config"]["Image"],
                "image_id": info["Image"],
                "repo_digests": image.get("RepoDigests", []),
                "cpus": host["NanoCpus"] / 1e9 if host.get("NanoCpus") else None,
                "memory_bytes": host.get("Memory") or None,
                "state": info["State"]["Status"],
            }
        )
    return out


def postgres_info(dsn: str) -> dict:
    import psycopg

    with psycopg.connect(dsn) as conn:
        version = conn.execute("SELECT version()").fetchone()[0]
        changed = conn.execute(
            "SELECT name, setting FROM pg_settings "
            "WHERE source NOT IN ('default', 'override', 'client', 'session') ORDER BY name"
        ).fetchall()
    return {"version": version, "non_default_settings": dict(changed)}


def host_info() -> dict:
    cpuinfo = Path("/proc/cpuinfo").read_text()
    model = next(
        (line.split(":", 1)[1].strip() for line in cpuinfo.splitlines() if line.startswith("model name")), None
    )
    meminfo = Path("/proc/meminfo").read_text().splitlines()
    mem_kb = int(next(line for line in meminfo if line.startswith("MemTotal")).split()[1])
    os_release = dict(line.split("=", 1) for line in Path("/etc/os-release").read_text().splitlines() if "=" in line)
    return {
        "cpu_model": model,
        "cores": os.cpu_count(),
        "ram_bytes": mem_kb * 1024,
        "os": os_release.get("PRETTY_NAME", "").strip('"'),
        "kernel": platform.release(),
        "docker": run("docker", "version", "--format", "{{.Server.Version}}"),
        "docker_compose": run("docker", "compose", "version", "--short"),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--target-dir", type=Path, required=True)
    p.add_argument("--scenario", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--profile", required=True)
    p.add_argument("--k6-image", required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()

    keys = os.environ.get("BENCH_CONFIG_KEYS", "").split()
    overrides = os.environ.get("BENCH_SHELL_KEYS", "").split()
    versions = {"k6": run("docker", "run", "--rm", a.k6_image, "version")}
    if os.environ.get("PG_DSN"):
        versions["postgres"] = postgres_info(os.environ["PG_DSN"])
    hook = a.target_dir / "hooks" / "versions"
    if os.access(hook, os.X_OK):
        versions.update(json.loads(run(str(hook)) or "{}"))

    meta = {
        "timestamp": datetime.now(UTC).isoformat(),
        "scenario": a.scenario,
        "target": a.target,
        "profile": a.profile,
        "git": git_info(a.root),
        "env": {k: os.environ.get(k) for k in keys},
        "env_overrides": sorted(overrides),
        "k6_image": a.k6_image,
        "containers": containers(),
        "versions": versions,
        "host": host_info(),
    }
    a.out.write_text(json.dumps(meta, indent=2) + "\n")


if __name__ == "__main__":
    main()
