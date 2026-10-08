export const RISK_META = {
  LOW: { color: '#22c55e', bg: 'rgba(34,197,94,0.12)', label: 'Low Risk', hex: '#22c55e' },
  MODERATE: { color: '#eab308', bg: 'rgba(234,179,8,0.12)', label: 'Moderate Risk', hex: '#eab308' },
  HIGH: { color: '#f97316', bg: 'rgba(249,115,22,0.14)', label: 'High Risk', hex: '#f97316' },
  CRITICAL: { color: '#ef4444', bg: 'rgba(239,68,68,0.16)', label: 'Critical Risk', hex: '#ef4444' },
}

export const riskMeta = (level) => RISK_META[level] || RISK_META.LOW

/**
 * Display-only snapshot of the canonical thresholds in `backend/app/risk.py`
 * (`RISK_LEVELS`) and `ml/model/model_meta.json` (`risk_thresholds`).
 * `upper_bound` is inclusive. The backend stays the only authority that
 * assigns `risk_level`; this constant exists purely so the UI can show the
 * band the score fell into. Keep in sync if the artifact changes.
 */
export const RISK_THRESHOLDS = [
  { level: 'LOW', upper: 30 },
  { level: 'MODERATE', upper: 60 },
  { level: 'HIGH', upper: 80 },
  { level: 'CRITICAL', upper: 100 },
]

/** Score → the level the backend would assign (mirrors `classify_risk`). */
export function bandForScore(score) {
  const value = Number(score) || 0
  for (const band of RISK_THRESHOLDS) {
    if (value <= band.upper) return band.level
  }
  return RISK_THRESHOLDS[RISK_THRESHOLDS.length - 1].level
}


export const markerColor = (level) => riskMeta(level).color

export function formatScore(score) {
  return Number(score || 0).toFixed(0)
}

export function formatTs(ts) {
  if (!ts) return '—'
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })
}

export function formatDateShort(ts) {
  if (!ts) return '—'
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}

/**
 * Age of an API timestamp relative to now, e.g. "12s ago" / "4m ago".
 * Returns null when the timestamp is missing or unparseable so callers can
 * show "unknown" instead of inventing a freshness value.
 */
export function relativeAge(ts, now = Date.now()) {
  if (!ts) return null
  const t = new Date(ts).getTime()
  if (Number.isNaN(t)) return null
  const secs = Math.max(0, Math.round((now - t) / 1000))
  if (secs < 60) return `${secs}s ago`
  const mins = Math.round(secs / 60)
  if (mins < 60) return `${mins}m ago`
  const hours = Math.round(mins / 60)
  if (hours < 48) return `${hours}h ago`
  return `${Math.round(hours / 24)}d ago`
}

export const NER_STATES = [
  'Arunachal Pradesh',
  'Assam',
  'Manipur',
  'Meghalaya',
  'Mizoram',
  'Nagaland',
  'Sikkim',
  'Tripura',
]