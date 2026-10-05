export const RISK_META = {
  LOW: { color: '#22c55e', bg: 'rgba(34,197,94,0.12)', label: 'Low Risk', hex: '#22c55e' },
  MODERATE: { color: '#eab308', bg: 'rgba(234,179,8,0.12)', label: 'Moderate Risk', hex: '#eab308' },
  HIGH: { color: '#f97316', bg: 'rgba(249,115,22,0.14)', label: 'High Risk', hex: '#f97316' },
  CRITICAL: { color: '#ef4444', bg: 'rgba(239,68,68,0.16)', label: 'Critical Risk', hex: '#ef4444' },
}

export const riskMeta = (level) => RISK_META[level] || RISK_META.LOW

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