import { describe, it, expect, beforeEach } from 'vitest'
import {
  saveDashboardSummary,
  loadDashboardSummary,
  clearDashboardSummary,
  DASHBOARD_SUMMARY_KEY,
} from '../services/offlineCache'

const VALID = {
  total_locations: 30,
  overall_risk_level: 'HIGH',
  overall_avg_score: 61.2,
  avg_confidence: 72.5,
  risk_counts: { LOW: 10, MODERATE: 8, HIGH: 9, CRITICAL: 3 },
  highest_risk_location: {
    name: 'Yuksom',
    state: 'Sikkim',
    risk_score: 88,
    risk_level: 'CRITICAL',
  },
  data_source: 'DEMO',
  live_degraded: false,
}

describe('offline dashboard cache', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('round-trips a sanitized summary with a saved timestamp', () => {
    expect(saveDashboardSummary(VALID)).toBe(true)

    const entry = loadDashboardSummary()
    expect(entry).toBeTruthy()
    expect(typeof entry.saved_at).toBe('string')
    expect(Number.isNaN(Date.parse(entry.saved_at))).toBe(false)
    expect(entry.summary.total_locations).toBe(30)
    expect(entry.summary.risk_counts.CRITICAL).toBe(3)
    expect(entry.summary.highest_risk_location.name).toBe('Yuksom')
  })

  it('never persists secrets, tokens, users, alerts or predictions', () => {
    saveDashboardSummary({
      ...VALID,
      token: 'secret-jwt-value',
      access_token: 'another-secret',
      user: { email: 'admin@landslideguard.ai', role: 'admin' },
      alerts: [{ message: 'sensitive alert detail' }],
      predictions: [{ risk_score: 99 }],
    })

    const raw = localStorage.getItem(DASHBOARD_SUMMARY_KEY)
    expect(raw).not.toContain('secret-jwt-value')
    expect(raw).not.toContain('another-secret')
    expect(raw).not.toContain('admin@landslideguard.ai')
    expect(raw).not.toContain('sensitive alert detail')

    const entry = loadDashboardSummary()
    expect(entry.summary).not.toHaveProperty('token')
    expect(entry.summary).not.toHaveProperty('user')
    expect(entry.summary).not.toHaveProperty('alerts')
    expect(entry.summary).not.toHaveProperty('predictions')
  })

  it('returns null and purges malformed JSON', () => {
    localStorage.setItem(DASHBOARD_SUMMARY_KEY, '{not valid json')
    expect(loadDashboardSummary()).toBeNull()
    expect(localStorage.getItem(DASHBOARD_SUMMARY_KEY)).toBeNull()
  })

  it('returns null for an outdated schema version and clears it', () => {
    localStorage.setItem(
      DASHBOARD_SUMMARY_KEY,
      JSON.stringify({ version: 0, saved_at: new Date().toISOString(), summary: VALID })
    )
    expect(loadDashboardSummary()).toBeNull()
    expect(localStorage.getItem(DASHBOARD_SUMMARY_KEY)).toBeNull()
  })

  it('returns null for a structurally invalid summary', () => {
    localStorage.setItem(
      DASHBOARD_SUMMARY_KEY,
      JSON.stringify({
        version: 1,
        saved_at: new Date().toISOString(),
        summary: { risk_counts: 'not-an-object' },
      })
    )
    expect(loadDashboardSummary()).toBeNull()
  })

  it('returns null for an unparseable saved_at timestamp', () => {
    localStorage.setItem(
      DASHBOARD_SUMMARY_KEY,
      JSON.stringify({ version: 1, saved_at: 'not-a-date', summary: VALID })
    )
    expect(loadDashboardSummary()).toBeNull()
  })

  it('exposes a clear helper', () => {
    saveDashboardSummary(VALID)
    expect(loadDashboardSummary()).toBeTruthy()
    clearDashboardSummary()
    expect(loadDashboardSummary()).toBeNull()
  })
})
