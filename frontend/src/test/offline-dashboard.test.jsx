import React from 'react'
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import OfflineDashboard from '../components/OfflineDashboard'

const CACHED = {
  saved_at: '2026-10-12T09:30:00.000Z',
  summary: {
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
  },
}

describe('OfflineDashboard (stale read-only fallback)', () => {
  it('labels the snapshot STALE / LAST UPDATED and shows cached values', () => {
    render(
      <MemoryRouter>
        <OfflineDashboard cached={CACHED} />
      </MemoryRouter>
    )

    expect(screen.getAllByText(/stale/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/last updated/i).length).toBeGreaterThan(0)
    expect(screen.getByRole('status')).toHaveTextContent(/offline/i)
    expect(screen.getByText('30')).toBeInTheDocument()
    expect(screen.getByText('Yuksom')).toBeInTheDocument()
    // The source must still be disclosed (DEMO stays visible).
    expect(screen.getByText(/demo data/i)).toBeInTheDocument()
  })

  it('renders nothing when there is no cached summary', () => {
    const { container } = render(
      <MemoryRouter>
        <OfflineDashboard cached={null} />
      </MemoryRouter>
    )
    expect(container).toBeEmptyDOMElement()
  })
})
