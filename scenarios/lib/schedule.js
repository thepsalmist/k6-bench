import exec from 'k6/execution';

// Timeline: warmup, then for each step an optional ramp followed by a hold.
// Only "hold" segments are meant for analysis.
export function buildSchedule({ warmup, ramp, hold, steps }) {
  const rates = steps.map(Number);
  if (new Set(rates).size !== rates.length) throw new Error(`step rates must be unique: ${steps}`);
  const segments = [];
  let t = 0;
  const push = (phase, step, rate, duration) => {
    if (duration <= 0) return;
    segments.push({ phase, step, rate, start: t, end: t + duration });
    t += duration;
  };
  push('warmup', 'warmup', 0, warmup);
  for (const rate of rates) {
    push('ramp', String(rate), rate, ramp);
    push('hold', String(rate), rate, hold);
  }
  return { segments, total: t };
}

export function rampingStages(schedule) {
  return schedule.segments.map((s) => ({ target: s.rate, duration: `${s.end - s.start}s` }));
}

export function holdSteps(schedule) {
  return schedule.segments.filter((s) => s.phase === 'hold');
}

export function segmentAt(schedule, seconds) {
  const segs = schedule.segments;
  return segs.find((s) => seconds < s.end) || segs[segs.length - 1];
}

export function currentSegment(schedule) {
  return segmentAt(schedule, exec.instance.currentTestRunDuration / 1000);
}

export function stepTags(schedule) {
  const seg = currentSegment(schedule);
  return { step: seg.step, phase: seg.phase };
}

// Wall-clock time at which test-run duration was zero. Step tags and schedule.json share this clock;
// executors start after setup(), so keep setup() trivial.
export function runStartEpochMs() {
  return Date.now() - exec.instance.currentTestRunDuration;
}
