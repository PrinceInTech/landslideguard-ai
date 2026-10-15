/**
 * Minimal, sanitized offline cache for the dashboard summary.
 *
 * Only the aggregate, non-sensitive risk summary is ever persisted. This module
 * deliberately whitelists fields — it never stores credentials, JWTs, user
 * profile data, admin data, alert details, the monitored-location list or any
 * prediction output, even if a caller passes them in.
 *
 * Stored shape (localStorage, JSON):
 *   { version: 1, saved_at: <ISO string>, summary: { ...whitelisted fields } }
 */

export const DASHBOARD_SUMMARY_KEY = 'lg_offline_risk_summary'
const SCHEMA_VERSION = 1
const ALLOWED_LEVELS = ['LOW', 'MODERATE', 'HIGH', 'CRITICAL']

const isFiniteNumber = (v) => typeof v === 'number' && Number.isFinite(v)
const isLevel = (v) => ALLOWED_LEVELS.includes(v)

function toFiniteNumber(value, fallback = 0) {
  const n = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(n) ? n : fallback
}

/**
 * Rebuild a summary from a whitelist of fields. Returns null when the input is
 * not a usable summary so callers can safely ignore malformed data.
 */
export function sanitizeDashboardSummary(raw) {
  if (!raw || typeof raw !== 'object') return null

  const counts = raw.risk_counts
  if (!counts || typeof counts !== 'object') return null

  const risk_counts = {}
  for (const level of ALLOWED_LEVELS) {
    risk_counts[level] = toFiniteNumber(counts[level])
  }

  let highest_risk_location = null
  const highest = raw.highest_risk_location
  if (
    highest &&
    typeof highest === 'object' &&
    typeof highest.name === 'string' &&
    typeof highest.state === 'string' &&
    isLevel(highest.risk_level)
  ) {
    highest_risk_location = {
      name: highest.name,
      state: highest.state,
      risk_score: toFiniteNumber(highest.risk_score),
      risk_level: highest.risk_level,
    }
  }

  const data_source =
    raw.data_source === 'LIVE' ? 'LIVE' : raw.data_source === 'DEMO' ? 'DEMO' : 'UNKNOWN'

  return {
    total_locations: toFiniteNumber(raw.total_locations),
    overall_risk_level: isLevel(raw.overall_risk_level) ? raw.overall_risk_level : 'LOW',
    overall_avg_score: toFiniteNumber(raw.overall_avg_score),
    avg_confidence: toFiniteNumber(raw.avg_confidence),
    risk_counts,
    data_source,
    live_degraded: Boolean(raw.live_degraded),
    highest_risk_location,
  }
}

/** Persist a sanitized summary. Returns true when something was written. */
export function saveDashboardSummary(summary) {
  const clean = sanitizeDashboardSummary(summary)
  if (!clean) return false
  try {
    localStorage.setItem(
      DASHBOARD_SUMMARY_KEY,
      JSON.stringify({ version: SCHEMA_VERSION, saved_at: new Date().toISOString(), summary: clean })
    )
    return true
  } catch {
    return false
  }
}

/**
 * Load a validated summary. Malformed JSON, a wrong/old schema version or a
 * structurally invalid payload are purged and reported as null.
 */
export function loadDashboardSummary() {
  let raw
  try {
    raw = localStorage.getItem(DASHBOARD_SUMMARY_KEY)
  } catch {
    return null
  }
  if (!raw) return null

  let parsed
  try {
    parsed = JSON.parse(raw)
  } catch {
    clearDashboardSummary()
    return null
  }

  if (
    !parsed ||
    parsed.version !== SCHEMA_VERSION ||
    typeof parsed.saved_at !== 'string' ||
    Number.isNaN(Date.parse(parsed.saved_at))
  ) {
    clearDashboardSummary()
    return null
  }

  const clean = sanitizeDashboardSummary(parsed.summary)
  if (!clean) {
    clearDashboardSummary()
    return null
  }

  return { saved_at: parsed.saved_at, summary: clean }
}

export function clearDashboardSummary() {
  try {
    localStorage.removeItem(DASHBOARD_SUMMARY_KEY)
  } catch {
    /* ignore */
  }
}
