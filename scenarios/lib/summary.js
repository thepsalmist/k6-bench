const TAG_RE = /^([^{]+)\{(.*)\}$/;

function parseSubmetric(name) {
  const m = name.match(TAG_RE);
  if (!m) return null;
  const tags = {};
  for (const pair of m[2].split(',')) {
    const i = pair.indexOf(':');
    tags[pair.slice(0, i)] = pair.slice(i + 1);
  }
  return { metric: m[1], tags };
}

// Rows of per-step stats for every submetric tagged with step + phase:hold.
export function stepRows(data, schedule, expectedRates = {}) {
  const holds = Object.fromEntries(
    schedule.segments.filter((s) => s.phase === 'hold').map((s) => [s.step, s]),
  );
  const rows = {};
  for (const [name, metric] of Object.entries(data.metrics)) {
    const sub = parseSubmetric(name);
    if (!sub || sub.tags.phase !== 'hold' || !(sub.tags.step in holds)) continue;
    const { step, phase, ...rest } = sub.tags;
    const group = Object.values(rest).join(' ');
    const key = `${step}|${group}`;
    const seg = holds[step];
    rows[key] = rows[key] || { step, rate: seg.rate, group, seconds: seg.end - seg.start };
    if (sub.metric === 'http_req_duration') {
      const v = metric.values;
      Object.assign(rows[key], {
        count: v.count, p50: v.med, p95: v['p(95)'], p99: v['p(99)'], max: v.max,
      });
    } else if (sub.metric === 'http_req_failed') {
      rows[key].failed = metric.values.rate;
    }
  }
  for (const row of Object.values(rows)) {
    const expected = expectedRates[row.group] && expectedRates[row.group](row.rate);
    if (expected > 0 && row.count !== undefined) {
      row.expected_per_s = expected;
      row.achieved_ratio = row.count / row.seconds / expected;
    }
  }
  return Object.values(rows).sort((a, b) => a.rate - b.rate || a.group.localeCompare(b.group));
}

// A step whose load generator fell this far behind target measured saturation, not the target rate.
const UNDER_RATE = 0.95;
const pad = (v, n) => String(v).padStart(n);
const ms = (v) => (v === undefined ? '-' : v.toFixed(1));

export function stepTable(rows) {
  const head = `${pad('step', 6)}  ${'group'.padEnd(18)}${pad('req/s', 8)}${pad('p50 ms', 9)}${pad('p95 ms', 9)}${pad('p99 ms', 9)}${pad('max ms', 9)}${pad('fail%', 7)}`;
  const lines = rows.map((r) => [
    pad(r.step, 6), ' ', ' ', r.group.padEnd(18),
    pad(r.count === undefined ? '-' : (r.count / r.seconds).toFixed(1), 8),
    pad(ms(r.p50), 9), pad(ms(r.p95), 9), pad(ms(r.p99), 9), pad(ms(r.max), 9),
    pad(r.failed === undefined ? '-' : (r.failed * 100).toFixed(2), 7),
    r.achieved_ratio < UNDER_RATE ? `  UNDER RATE (${(r.achieved_ratio * 100).toFixed(0)}% of target)` : '',
  ].join(''));
  return [head, ...lines].join('\n');
}

export function makeHandleSummary(schedule, outDir, expectedRates = {}) {
  return function handleSummary(data) {
    const endMs = Date.now();
    const startMs = (data.setup_data && data.setup_data.startEpochMs) || endMs - data.state.testRunDurationMs;
    const rows = stepRows(data, schedule, expectedRates);
    const dropped = Object.entries(data.metrics)
      .filter(([name]) => name.startsWith('dropped_iterations'))
      .map(([name, m]) => `${name}: ${m.values.count}`);
    const text = [
      '',
      'per-step results (hold phases only):',
      stepTable(rows),
      '',
      ...dropped,
      '',
    ].join('\n');
    return {
      stdout: text,
      [`${outDir}/summary.json`]: JSON.stringify(data, null, 2),
      [`${outDir}/steps.json`]: JSON.stringify(rows, null, 2),
      [`${outDir}/schedule.json`]: JSON.stringify(
        { start_epoch_ms: startMs, end_epoch_ms: endMs, ...schedule }, null, 2,
      ),
    };
  };
}
