import argparse
import json
import sys
import time
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

QUERIES = {
    "activity": """
        SELECT state, wait_event_type, wait_event, count(*) AS n
        FROM pg_stat_activity
        WHERE datname = current_database() AND pid <> pg_backend_pid()
        GROUP BY 1, 2, 3
    """,
    "database": """
        SELECT numbackends, xact_commit, xact_rollback, blks_read, blks_hit,
               tup_returned, tup_fetched, tup_inserted, tup_updated, tup_deleted,
               deadlocks, temp_bytes
        FROM pg_stat_database WHERE datname = current_database()
    """,
    "tables": """
        SELECT relname, n_live_tup, n_dead_tup, n_tup_ins, n_tup_upd, n_tup_hot_upd, n_tup_del,
               seq_scan, idx_scan, autovacuum_count, autoanalyze_count,
               extract(epoch FROM last_autovacuum) AS last_autovacuum,
               pg_total_relation_size(relid) AS total_bytes
        FROM pg_stat_user_tables
    """,
    "locks": """
        SELECT locktype, mode, granted, count(*) AS n
        FROM pg_locks
        WHERE database IS NULL
           OR database IN (0, (SELECT oid FROM pg_database WHERE datname = current_database()))
        GROUP BY 1, 2, 3
    """,
}


def sample(conn: psycopg.Connection) -> dict:
    out = {"ts": round(time.time(), 3)}
    for name, sql in QUERIES.items():
        rows = conn.execute(sql).fetchall()
        out[name] = rows[0] if name == "database" else rows
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Sample Postgres statistics views to JSONL")
    p.add_argument("--dsn", required=True)
    p.add_argument("--interval", type=float, default=10)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()

    conn = None
    with a.out.open("w") as f:
        while True:
            started = time.time()
            try:
                conn = conn or psycopg.connect(a.dsn, autocommit=True, row_factory=dict_row)
                f.write(json.dumps(sample(conn), default=float) + "\n")
                f.flush()
            except psycopg.Error as exc:
                print(f"sample_pg: {exc}", file=sys.stderr, flush=True)
                conn = None
            time.sleep(max(0.0, a.interval - (time.time() - started)))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
