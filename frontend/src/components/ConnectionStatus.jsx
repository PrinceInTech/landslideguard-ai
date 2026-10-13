import React from 'react'
import { Wifi, WifiOff } from 'lucide-react'
import { useOnlineStatus } from '../hooks/useOnlineStatus'

/**
 * Accessible indicator of the browser's connectivity.
 *
 * It reports *frontend* (browser) availability only. Backend/API availability
 * is deliberately a separate concern confirmed per request (error states,
 * DataSourceBadge, etc.), so this never implies the API is reachable.
 */
export function ConnectionStatus({ className = '' }) {
  const { isOnline } = useOnlineStatus()

  return (
    <span
      role="status"
      aria-live="polite"
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold ${
        isOnline ? 'bg-emerald-500/15 text-emerald-400' : 'bg-red-500/15 text-red-400'
      } ${className}`}
      title={
        isOnline
          ? 'Your browser reports a network connection. This does not guarantee the backend API is reachable — that is confirmed per request.'
          : 'Your browser is offline. Live data and actions that need the backend are unavailable; last known data may be shown.'
      }
    >
      {isOnline ? (
        <Wifi className="h-3.5 w-3.5" aria-hidden="true" />
      ) : (
        <WifiOff className="h-3.5 w-3.5" aria-hidden="true" />
      )}
      {isOnline ? 'Online' : 'Offline'}
      <span className="sr-only">
        {isOnline
          ? ' — browser network connection detected, backend reachability is confirmed per request'
          : ' — no browser network connection'}
      </span>
    </span>
  )
}

export default ConnectionStatus
