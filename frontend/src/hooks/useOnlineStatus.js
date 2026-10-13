import { useEffect, useState } from 'react'

/**
 * Tracks the browser's own online/offline state and keeps it in sync with the
 * `online` / `offline` window events (listeners are removed on cleanup).
 *
 * Important: `navigator.onLine === true` only means the browser believes it has
 * a network interface. It does NOT prove the backend/API is reachable — a
 * captive portal, a downed server or a blocked CORS layer all look "online".
 * Callers must confirm API availability from the actual request result.
 */
export function useOnlineStatus() {
  const [isOnline, setIsOnline] = useState(() =>
    typeof navigator === 'undefined' ? true : navigator.onLine !== false
  )

  useEffect(() => {
    const goOnline = () => setIsOnline(true)
    const goOffline = () => setIsOnline(false)

    window.addEventListener('online', goOnline)
    window.addEventListener('offline', goOffline)
    // Re-read once the listeners exist so a change between render and effect is
    // not missed.
    setIsOnline(navigator.onLine !== false)

    return () => {
      window.removeEventListener('online', goOnline)
      window.removeEventListener('offline', goOffline)
    }
  }, [])

  return { isOnline, isOffline: !isOnline }
}

export default useOnlineStatus
