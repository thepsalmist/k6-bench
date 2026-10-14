#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 <scenario> <target> [profile]" >&2
  exit 2
}
[[ $# -ge 2 ]] || usage

SCENARIO=$1
TARGET=$2
PROFILE=${3:-default}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
TARGET_DIR=$ROOT/targets/$TARGET
SCENARIO_FILE=$ROOT/scenarios/$SCENARIO.js

[[ -f $TARGET_DIR/compose.yml ]] || { echo "unknown target: $TARGET" >&2; exit 2; }
[[ -f $SCENARIO_FILE ]] || { echo "unknown scenario: $SCENARIO" >&2; exit 2; }
[[ -f $ROOT/profiles/$PROFILE.env ]] || { echo "unknown profile: $PROFILE" >&2; exit 2; }

K6_IMAGE=${K6_IMAGE:-grafana/k6:2.3.0}
HEALTH_TIMEOUT=${HEALTH_TIMEOUT:-300}
DRAIN_TIMEOUT=${DRAIN_TIMEOUT:-300}
SAMPLE_INTERVAL=${SAMPLE_INTERVAL:-10}

env_keys() { grep -Ev '^[[:space:]]*(#|$)' "$1" | cut -d= -f1; }

# Precedence: shell env > named profile > default profile > target.env.
SHELL_KEYS=()
for key in $(env_keys "$ROOT/profiles/default.env"; env_keys "$ROOT/profiles/$PROFILE.env"; env_keys "$TARGET_DIR/target.env"; compgen -e | grep '^SCENARIO_' || true); do
  [[ -n ${!key+x} ]] && SHELL_KEYS+=("$key")
done

load_env() {
  local key val
  while IFS= read -r line; do
    [[ $line =~ ^[[:space:]]*(#|$) ]] && continue
    key=${line%%=*}
    val=${line#*=}
    [[ -n ${!key+x} ]] || export "$key=$val"
  done <"$1"
}
load_env "$ROOT/profiles/$PROFILE.env"
load_env "$ROOT/profiles/default.env"
load_env "$TARGET_DIR/target.env"

CONFIG_KEYS=$( (env_keys "$ROOT/profiles/default.env"; env_keys "$ROOT/profiles/$PROFILE.env"; env_keys "$TARGET_DIR/target.env"; compgen -e | grep '^SCENARIO_' || true) | sort -u | tr '\n' ' ')

STAMP=$(date -u +%Y-%m-%dT%H%M%SZ)
NAME=$STAMP-$SCENARIO-$TARGET
[[ $PROFILE == default ]] || NAME=$NAME-$PROFILE
RES=$ROOT/results/$NAME
mkdir -p "$RES"

export COMPOSE_PROJECT_NAME=k6b-$TARGET
export COMPOSE_FILE=$TARGET_DIR/compose.yml
# Run the venv python directly, never via uv run or a shell function, so $! is the python PID and kill reaches it.
uv sync --quiet --project "$ROOT"
PY=$ROOT/.venv/bin/python
log() { echo "[run.sh $(date -u +%H:%M:%S)] $*" >&2; }

SAMPLER_PIDS=()
stop_samplers() {
  for pid in "${SAMPLER_PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
  for pid in "${SAMPLER_PIDS[@]}"; do wait "$pid" 2>/dev/null || true; done
  SAMPLER_PIDS=()
}
teardown() {
  stop_samplers
  docker compose logs --no-color --timestamps >"$RES/compose.log" 2>&1 || true
  if [[ ${KEEP_UP:-0} == 1 ]]; then
    log "KEEP_UP=1, leaving $COMPOSE_PROJECT_NAME running"
  else
    docker compose down -v --remove-orphans >/dev/null 2>&1 || true
  fi
  log "results: $RES"
}
trap teardown EXIT

log "starting $TARGET ($COMPOSE_PROJECT_NAME), profile=$PROFILE"
docker compose down -v --remove-orphans >/dev/null 2>&1 || true
docker compose up -d --build --quiet-pull

log "waiting for $APP_URL/healthz"
deadline=$((SECONDS + HEALTH_TIMEOUT))
until curl -fs --max-time 5 -o /dev/null "$APP_URL/healthz"; do
  ((SECONDS < deadline)) || { log "healthz timed out"; exit 1; }
  sleep 2
done

if [[ -x $TARGET_DIR/hooks/seed ]]; then
  log "seeding"
  "$TARGET_DIR/hooks/seed"
fi

BENCH_CONFIG_KEYS=$CONFIG_KEYS BENCH_SHELL_KEYS="${SHELL_KEYS[*]}" \
  "$PY" "$ROOT/scripts/meta.py" --root "$ROOT" --target-dir "$TARGET_DIR" \
  --scenario "$SCENARIO" --target "$TARGET" --profile "$PROFILE" \
  --k6-image "$K6_IMAGE" --out "$RES/meta.json"

if [[ -n ${PG_DSN:-} ]]; then
  "$PY" "$ROOT/scripts/sample_pg.py" --dsn "$PG_DSN" --interval "$SAMPLE_INTERVAL" --out "$RES/pg.jsonl" >>"$RES/samplers.log" 2>&1 &
  SAMPLER_PIDS+=($!)
fi
"$PY" "$ROOT/scripts/sample_containers.py" --project "$COMPOSE_PROJECT_NAME" --interval "$SAMPLE_INTERVAL" --out "$RES/containers.csv" >>"$RES/samplers.log" 2>&1 &
SAMPLER_PIDS+=($!)

K6_ENV=(-e "APP_URL=$APP_URL")
for key in $(compgen -e | grep '^SCENARIO_' || true); do K6_ENV+=(-e "$key=${!key}"); done

log "running k6 $SCENARIO"
k6_status=0
docker run --rm --network host --user "$(id -u):$(id -g)" \
  -v "$ROOT/scenarios:/scenarios:ro" -v "$RES:/out" \
  "${K6_ENV[@]}" "$K6_IMAGE" run --quiet \
  --out json=/out/k6.json.gz "/scenarios/$SCENARIO.js" 2>&1 | tee "$RES/k6.log" || k6_status=$?

if [[ -n ${JOB_TABLE:-} && -f $RES/schedule.json ]]; then
  log "collecting jobs from $JOB_TABLE"
  "$PY" "$ROOT/scripts/collect_jobs.py" --dsn "${PG_DSN:?JOB_TABLE requires PG_DSN}" --table "$JOB_TABLE" \
    --schedule "$RES/schedule.json" --drain-timeout "$DRAIN_TIMEOUT" --out "$RES"
fi

exit "$k6_status"
