export function envString(name, fallback) {
  const v = __ENV[name];
  return v === undefined || v === '' ? fallback : v;
}

export function envNumber(name, fallback) {
  const n = Number(envString(name, fallback));
  if (!Number.isFinite(n)) throw new Error(`${name} must be a number`);
  return n;
}

export function envList(name, fallback) {
  return envString(name, fallback).split(',').map((s) => s.trim()).filter(Boolean);
}

// "90", "90s", "3m", "1m30s", "1h" -> seconds
export function parseDuration(text) {
  const s = String(text).trim();
  if (/^\d+(\.\d+)?$/.test(s)) return Number(s);
  const parts = s.match(/^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?$/);
  if (!parts || s === '') throw new Error(`bad duration: ${text}`);
  return Number(parts[1] || 0) * 3600 + Number(parts[2] || 0) * 60 + Number(parts[3] || 0);
}

export function envDuration(name, fallback) {
  return parseDuration(envString(name, fallback));
}
