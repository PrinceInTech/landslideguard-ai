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

/** Polling variant for live monitors. */
export function usePolling(path, intervalMs = 15000, deps = []) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = async () => {
    try {
      const res = await api.get(path)
      setData(res.data)
      setError(null)
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    const timer = setInterval(load, intervalMs)
    return () => clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, ...deps])

  return { data, loading, error, reload: load }
}