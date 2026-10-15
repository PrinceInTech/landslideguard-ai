import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import ConnectionStatus from '../components/ConnectionStatus'
import { useOnlineStatus } from '../hooks/useOnlineStatus'

describe('connection status indicator', () => {
  it('shows online by default and reacts to offline/online events', () => {
    render(<ConnectionStatus />)
    expect(screen.getByRole('status')).toHaveTextContent(/online/i)

    act(() => {
      window.dispatchEvent(new Event('offline'))
    })
    expect(screen.getByRole('status')).toHaveTextContent(/offline/i)

    act(() => {
      window.dispatchEvent(new Event('online'))
    })
    expect(screen.getByRole('status')).toHaveTextContent(/online/i)
  })

  it('is exposed to assistive tech via role="status"', () => {
    render(<ConnectionStatus />)
    const status = screen.getByRole('status')
    expect(status).toHaveAttribute('aria-live', 'polite')
  })

  it('removes its online/offline listeners on unmount', () => {
    const addSpy = vi.spyOn(window, 'addEventListener')
    const removeSpy = vi.spyOn(window, 'removeEventListener')

    function Probe() {
      useOnlineStatus()
      return null
    }

    const { unmount } = render(<Probe />)

    const onlineAdd = addSpy.mock.calls.find(([type]) => type === 'online')
    const offlineAdd = addSpy.mock.calls.find(([type]) => type === 'offline')
    expect(onlineAdd).toBeTruthy()
    expect(offlineAdd).toBeTruthy()

    unmount()

    expect(removeSpy).toHaveBeenCalledWith('online', onlineAdd[1])
    expect(removeSpy).toHaveBeenCalledWith('offline', offlineAdd[1])
  })
})
