import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// Only the transport is mocked; the page and its hooks stay real.
vi.mock('../services/api', () => ({
  default: { get: vi.fn(), put: vi.fn() },
}))

import api from '../services/api'
import Alerts from '../pages/Alerts'

const RESOLVED_ALERT = {
  id: 7,
  location_name: 'Yuksom',
  location_state: 'Sikkim',
  risk_level: 'CRITICAL',
  risk_score: 88,
  message: 'CRITICAL LANDSLIDE WARNING - Yuksom, Sikkim.',
  trigger_factors: ['rainfall (40%)', 'slope (25%)'],
  status: 'resolved',
  created_at: '2026-10-12T09:30:00.000Z',
  resolved_at: '2026-10-12T11:00:00.000Z',
}

function renderAlerts() {
  return render(
    <MemoryRouter>
      <Alerts />
    </MemoryRouter>,
  )
}

describe('Alerts authority page', () => {
  beforeEach(() => {
    api.get.mockReset()
    api.put.mockReset()
  })

  it('distinguishes "no alerts issued" from "no filter matches"', async () => {
    api.get.mockResolvedValue({ data: [] })
    renderAlerts()

    await waitFor(() =>
      expect(screen.getByText('No alerts have been issued yet.')).toBeInTheDocument(),
    )

    // Applying a filter while the result set is empty switches the message.
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'resolved' } })
    await waitFor(() =>
      expect(screen.getByText('No alerts match the current filters.')).toBeInTheDocument(),
    )
  })

  it('lets a resolved alert be expanded and shows its lifecycle with the resolved time', async () => {
    api.get.mockResolvedValue({ data: [RESOLVED_ALERT] })
    renderAlerts()

    await waitFor(() => expect(screen.getByText('Yuksom')).toBeInTheDocument())

    // Regression guard: details were previously hidden for resolved alerts.
    const toggle = screen.getByRole('button', { name: 'View Details' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(toggle)

    await waitFor(() =>
      expect(screen.getByLabelText('Alert lifecycle')).toBeInTheDocument(),
    )
    const list = screen.getByLabelText('Alert lifecycle')
    expect(within(list).getByText('Issued')).toBeInTheDocument()
    expect(within(list).getByText('Resolved')).toBeInTheDocument()
    const values = Array.from(list.querySelectorAll('time')).map((t) =>
      t.getAttribute('datetime'),
    )
    expect(values).toContain(RESOLVED_ALERT.created_at)
    expect(values).toContain(RESOLVED_ALERT.resolved_at)

    // Trigger factors remain available in the expanded panel.
    expect(screen.getByText('rainfall (40%)')).toBeInTheDocument()
  })
})
