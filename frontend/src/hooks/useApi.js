import { useEffect, useState } from 'react'
import api from '../services/api'

/** Fetch hook with loading/error/data + reload. */
export function useApi(path, deps = []) {
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
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps])

  return { data, loading, error, reload: load }
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
    // Fetch immediately on mount, on resume and whenever deps change, then
    // keep going while not paused.
    load()
    if (paused) return undefined
    const timer = setInterval(load, intervalMs)
    return () => clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, paused, ...deps])

  return { data, loading, error, lastFetched, reload: load }
}