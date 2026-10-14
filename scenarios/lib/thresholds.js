// Thresholds that always pass. They exist so the end-of-test summary carries a
// submetric (and its percentiles) for every tag combination we analyse.
export function informational(entries) {
  const out = {};
  for (const { metric, tags, kind } of entries) {
    const filter = Object.entries(tags).map(([k, v]) => `${k}:${v}`).join(',');
    out[`${metric}{${filter}}`] = [{ rate: 'rate>=0', counter: 'count>=0' }[kind] || 'max>=0'];
  }
  return out;
}

export function perStep(holdSteps, groups) {
  const entries = [];
  for (const seg of holdSteps) {
    for (const g of groups) {
      if (g.when && !g.when(seg)) continue;
      const tags = { ...g.tags, step: seg.step, phase: 'hold' };
      entries.push({ metric: 'http_req_duration', tags, kind: 'trend' });
      entries.push({ metric: 'http_req_failed', tags, kind: 'rate' });
    }
  }
  return informational(entries);
}
