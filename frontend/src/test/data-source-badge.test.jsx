import React from 'react'
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import DataSourceBadge from '../components/DataSourceBadge'

// DEMO labeling must stay visible wherever the UI presents simulated data.
describe('DataSourceBadge demo labeling', () => {
  it('labels a DEMO source as DEMO DATA (never as live)', () => {
    render(<DataSourceBadge source="DEMO" />)
    expect(screen.getByText('DEMO DATA')).toBeInTheDocument()
  })

  it('labels a LIVE source as LIVE DATA', () => {
    render(<DataSourceBadge source="LIVE" />)
    expect(screen.getByText('LIVE DATA')).toBeInTheDocument()
  })

  it('labels a missing source as SOURCE UNKNOWN rather than DEMO', () => {
    render(<DataSourceBadge />)
    expect(screen.getByText('SOURCE UNKNOWN')).toBeInTheDocument()
  })

  it('labels a degraded LIVE source as LIVE UNAVAILABLE — DEMO DATA', () => {
    render(<DataSourceBadge source="LIVE" degraded />)
    expect(screen.getByText('LIVE UNAVAILABLE — DEMO DATA')).toBeInTheDocument()
  })
})
