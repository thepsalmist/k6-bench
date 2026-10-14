import http from 'k6/http';
import { check } from 'k6';
import { envDuration, envList, envNumber, envString } from './lib/env.js';
import { buildSchedule, holdSteps, rampingStages, runStartEpochMs, stepTags } from './lib/schedule.js';
import { informational, perStep } from './lib/thresholds.js';
import { makeHandleSummary } from './lib/summary.js';

const BASE = envString('APP_URL', 'http://127.0.0.1:18080');
const APP_RATE = envNumber('SCENARIO_APP_RATE', 50);
const WRITE_RATIO = envNumber('SCENARIO_WRITE_RATIO', 0.2);
const ITEM_COUNT = envNumber('SCENARIO_ITEM_COUNT', 100000);
const JOBS_PER_REQUEST = envNumber('SCENARIO_JOBS_PER_REQUEST', 1);
const MAX_VUS = envNumber('SCENARIO_MAX_VUS', 500);

const schedule = buildSchedule({
  warmup: envDuration('SCENARIO_WARMUP', '2m'),
  ramp: envDuration('SCENARIO_RAMP', '15s'),
  hold: envDuration('SCENARIO_HOLD', '3m'),
  steps: envList('SCENARIO_STEPS', '0,10,50,100,200,500'),
});

const GET_ITEM = 'GET /items/:id';
const POST_ITEM = 'POST /items';
const ENQUEUE = 'POST /enqueue';
const PARAMS = { timeout: '30s' };

export const options = {
  discardResponseBodies: true,
  summaryTrendStats: ['avg', 'min', 'med', 'p(95)', 'p(99)', 'max', 'count'],
  scenarios: {
    app_traffic: {
      executor: 'constant-arrival-rate',
      exec: 'appTraffic',
      rate: APP_RATE,
      timeUnit: '1s',
      duration: `${schedule.total}s`,
      preAllocatedVUs: Math.max(10, APP_RATE),
      maxVUs: MAX_VUS,
    },
    enqueue: {
      executor: 'ramping-arrival-rate',
      exec: 'enqueue',
      startRate: 0,
      // Stage targets are jobs/s; each iteration enqueues JOBS_PER_REQUEST jobs.
      timeUnit: `${JOBS_PER_REQUEST}s`,
      stages: rampingStages(schedule),
      preAllocatedVUs: 20,
      maxVUs: MAX_VUS,
    },
  },
  thresholds: {
    ...perStep(holdSteps(schedule), [
      { tags: { endpoint: GET_ITEM } },
      { tags: { endpoint: POST_ITEM } },
      { tags: { endpoint: ENQUEUE }, when: (seg) => seg.rate > 0 },
    ]),
    ...informational([
      { metric: 'dropped_iterations', tags: { scenario: 'app_traffic' }, kind: 'counter' },
      { metric: 'dropped_iterations', tags: { scenario: 'enqueue' }, kind: 'counter' },
    ]),
  },
};

function tagged(endpoint) {
  return { ...PARAMS, tags: { endpoint, name: endpoint, ...stepTags(schedule) } };
}

export function appTraffic() {
  if (Math.random() < WRITE_RATIO) {
    const body = JSON.stringify({ name: `item-${Date.now()}` });
    const res = http.post(`${BASE}/items`, body, {
      ...tagged(POST_ITEM),
      headers: { 'Content-Type': 'application/json' },
    });
    check(res, { 'POST /items 201': (r) => r.status === 201 });
  } else {
    const id = 1 + Math.floor(Math.random() * ITEM_COUNT);
    const res = http.get(`${BASE}/items/${id}`, tagged(GET_ITEM));
    check(res, { 'GET /items 200': (r) => r.status === 200 });
  }
}

export function enqueue() {
  const res = http.post(`${BASE}/enqueue?n=${JOBS_PER_REQUEST}`, null, tagged(ENQUEUE));
  check(res, { 'POST /enqueue 202': (r) => r.status === 202 });
}

export function setup() {
  return { startEpochMs: runStartEpochMs() };
}

export const handleSummary = makeHandleSummary(schedule, envString('K6_OUT_DIR', '/out'), {
  [ENQUEUE]: (jobRate) => jobRate / JOBS_PER_REQUEST,
});
