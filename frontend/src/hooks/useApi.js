import { useEffect, useState } from 'react'
import api from '../services/api'
import { useOnlineStatus } from './useOnlineStatus'

// Shown instead of firing a request that cannot succeed while the browser is
// offline. Kept as a constant so tests and callers can match on it.
export const OFFLINE_ERROR = 'You are offline — reconnect to load this data.'

/** Fetch hook with loading/error/data + reload. */
export function useApi(path, deps = []) {
  const { isOnline } = useOnlineStatus()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.get(path)
      setData(res.data)
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || 'Request failed')
      setData(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    // Do not fire a doomed request while offline; surface why instead. When
    // the browser comes back online the dependency change triggers a reload
    // through the normal API client.
    if (!isOnline) {
      setLoading(false)
      setError(OFFLINE_ERROR)
      return
    }
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOnline, ...deps])

  return { data, loading, error, reload: load, offline: !isOnline }
}

/**
 * Polling variant for live monitors.
 *
 * `opts.paused` stops the interval without dropping the already-loaded data,
 * so the UI can offer a real pause/resume control. `lastFetched` is the wall
 * clock of the last *successful* request — it says when we fetched, never when
 * the data itself is from (that is the API's own `last_updated`).
 */
export function usePolling(path, intervalMs = 15000, deps = [], opts = {}) {
  const paused = Boolean(opts.paused)
  const { isOnline } = useOnlineStatus()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastFetched, setLastFetched] = useState(null)

  const load = async () => {
    try {
      const res = await api.get(path)
      setData(res.data)
      setError(null)
      setLastFetched(new Date().toISOString())
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    // While offline, stop polling and keep the last good payload rather than
    // spamming failed requests. Coming back online re-runs this effect, which
    // refreshes through the normal API client.
    if (!isOnline) {
      setLoading(false)
      return undefined
    }
    // Fetch immediately on mount, on resume and whenever deps change, then
    // keep going while not paused.
    load()
    if (paused) return undefined
    const timer = setInterval(load, intervalMs)
    return () => clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, paused, isOnline, ...deps])

  return { data, loading, error, lastFetched, reload: load, offline: !isOnline }
}