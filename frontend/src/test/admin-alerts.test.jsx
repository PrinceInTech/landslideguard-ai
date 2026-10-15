import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../services/api', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}))

import api from '../services/api'
import Admin from '../pages/Admin'

const STATS = {
  total_locations: 5,
  total_alerts: 12,
  total_predictions: 3,
  total_users: 2,
  model_loaded: true,
  data_mode: 'DEMO',
}

const ALERTS = [
  {
    id: 1,
    location_name: 'Yuksom',
    risk_level: 'CRITICAL',
    message: 'critical message',
    status: 'resolved',
    created_at: '2026-10-12T09:30:00.000Z',
    resolved_at: '2026-10-12T11:00:00.000Z',
  },
  {
    id: 2,
    location_name: 'Nongstoin',
    risk_level: 'HIGH',
    message: 'high message',
    status: 'active',
    created_at: '2026-10-12T10:00:00.000Z',
    resolved_at: null,
  },
]

const SETTINGS = { data_mode: 'DEMO', weather_api_configured: false, model_present: true }

describe('Admin authority view', () => {
  beforeEach(() => {
    api.get.mockReset()
    api.get.mockImplementation((url) => {
      if (url === '/api/admin/stats') return Promise.resolve({ data: STATS })
      if (url === '/api/admin/alerts') return Promise.resolve({ data: ALERTS })
      if (url === '/api/admin/settings') return Promise.resolve({ data: SETTINGS })
      return Promise.reject(new Error(`unexpected request ${url}`))
    })
    // The page is admin-guarded; seed an admin session as the API would.
    localStorage.setItem('lg_user', JSON.stringify({ name: 'Admin', role: 'admin' }))
  })

  it('surfaces the data mode, the alert total and lifecycle timestamps', async () => {
    render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByText('DATA MODE: DEMO')).toBeInTheDocument())
    // Honest "showing N of total" instead of implying only 8 alerts exist.
    expect(screen.getByText('Showing 2 of 12')).toBeInTheDocument()
    expect(screen.getAllByText(/^Issued /)).toHaveLength(2)
    expect(screen.getByText(/^Resolved /)).toBeInTheDocument()
  })
})
