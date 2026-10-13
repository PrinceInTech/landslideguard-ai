import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act, waitFor } from '@testing-library/react'

// The hook under test must use the real API client module; only its transport
// (`api.get`) is mocked so no test ever touches a real network.
vi.mock('../services/api', () => ({
  default: { get: vi.fn() },
}))

import api from '../services/api'
import { usePolling } from '../hooks/useApi'

function Probe() {
  const { data, offline } = usePolling('/api/risk-summary', 60000)
  return (
    <div data-testid="out">
      {offline ? 'offline' : 'online'}:{data?.total_locations ?? 'none'}
    </div>
  )
}

describe('usePolling offline/reconnection behavior', () => {
  beforeEach(() => {
    api.get.mockReset()
  })

  it('fetches when online, stops when offline, and refreshes on reconnect', async () => {
    api.get.mockResolvedValue({ data: { total_locations: 30 } })

    render(<Probe />)
    await waitFor(() => expect(screen.getByTestId('out')).toHaveTextContent('online:30'))
    expect(api.get).toHaveBeenCalledTimes(1)

    // Going offline must not fire another request and must flip the flag.
    act(() => {
      window.dispatchEvent(new Event('offline'))
    })
    await waitFor(() => expect(screen.getByTestId('out')).toHaveTextContent('offline'))
    const callsWhileOffline = api.get.mock.calls.length

    // Reconnecting refreshes through the normal API client.
    api.get.mockResolvedValue({ data: { total_locations: 42 } })
    act(() => {
      window.dispatchEvent(new Event('online'))
    })
    await waitFor(() => expect(api.get.mock.calls.length).toBeGreaterThan(callsWhileOffline))
    await waitFor(() => expect(screen.getByTestId('out')).toHaveTextContent('online:42'))
  })
})
