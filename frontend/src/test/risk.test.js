import { describe, it, expect } from 'vitest'
import {
  bandForScore,
  riskMeta,
  RISK_META,
  formatScore,
  relativeAge,
} from '../utils/risk'

describe('risk-level display helpers', () => {
  it('maps scores to the level the backend assigns (inclusive upper bounds)', () => {
    expect(bandForScore(0)).toBe('LOW')
    expect(bandForScore(30)).toBe('LOW')
    expect(bandForScore(30.5)).toBe('MODERATE')
    expect(bandForScore(60)).toBe('MODERATE')
    expect(bandForScore(80)).toBe('HIGH')
    expect(bandForScore(100)).toBe('CRITICAL')
    expect(bandForScore(1000)).toBe('CRITICAL')
  })

  it('returns a display label per level and falls back to LOW for unknown', () => {
    expect(riskMeta('HIGH').label).toBe('High Risk')
    expect(riskMeta('CRITICAL').label).toBe('Critical Risk')
    expect(riskMeta('nonsense')).toBe(RISK_META.LOW)
  })

  it('formats a score to a whole number', () => {
    expect(formatScore(72.4)).toBe('72')
    expect(formatScore(undefined)).toBe('0')
  })

  it('reports age relative to a supplied clock and nulls bad input', () => {
    const now = Date.parse('2026-10-12T12:00:00Z')
    expect(relativeAge('2026-10-12T11:59:30Z', now)).toBe('30s ago')
    expect(relativeAge('2026-10-12T11:50:00Z', now)).toBe('10m ago')
    expect(relativeAge(null, now)).toBeNull()
    expect(relativeAge('not-a-date', now)).toBeNull()
  })
})
