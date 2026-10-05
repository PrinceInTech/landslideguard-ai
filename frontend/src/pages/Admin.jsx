import React, { useEffect, useState } from 'react'
import { ShieldCheck, Upload, RefreshCw, Zap, Database, Settings as SettingsIcon } from 'lucide-react'
import api from '../services/api'
import { PageState } from '../components/States'
import { useAuth } from '../hooks/useAuth'

export default function Admin() {
  const { isAuthed } = useAuth()
  const [stats, setStats] = useState(null)
  const [alerts, setAlerts] = useState([])
  const [settings, setSettings] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(null)
  const [notice, setNotice] = useState(null)
  const [file, setFile] = useState(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const [s, a, cfg] = await Promise.all([api.get('/api/admin/stats'), api.get('/api/admin/alerts'), api.get('/api/admin/settings')])
      setStats(s.data)
      setAlerts(a.data || [])
      setSettings(cfg.data)
    } catch (e) {
      if (e?.response?.status === 401 || e?.response?.status === 403) {
        setError('Admin access required — please log in with an admin account.')
      } else {
        setError(e?.response?.data?.detail || e.message)
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const run = async (action) => {
    setBusy(action)
    setNotice(null)
    try {
      let res
      if (action === 'retrain') res = await api.post('/api/admin/retrain')
      if (action === 'trigger') res = await api.post('/api/admin/trigger-predict')
      setNotice({ type: 'ok', text: res?.data?.message || 'Done' })
      load()
    } catch (e) {
      setNotice({ type: 'err', text: e?.response?.data?.detail || 'Action failed' })
    } finally {
      setBusy(null)
    }
  }

  const upload = async () => {
    if (!file) return
    setBusy('upload')
    setNotice(null)
    const fd = new FormData()
    fd.append('file', file)
    try {
      const res = await api.post('/api/admin/upload-dataset', fd)
      setNotice({ type: 'ok', text: res?.data?.message || 'Dataset uploaded' })
    } catch (e) {
      setNotice({ type: 'err', text: e?.response?.data?.detail || 'Upload failed' })
    } finally {
      setBusy(null)
    }
  }

  if (!isAuthed) {
    return (
      <div className="card flex flex-col items-center gap-3 py-16 text-center">
        <ShieldCheck className="h-10 w-10 text-slate-600" />
        <p className="font-bold text-slate-200">Admin access required</p>
        <p className="text-sm text-slate-400">Please sign in with an admin account to manage the system.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold text-slate-100">Admin Panel</h1>
        <p className="text-sm text-slate-400">System management for the disaster monitoring authority</p>
      </div>

      {notice && (
        <p className={`rounded-lg border px-4 py-2.5 text-sm ${notice.type === 'ok' ? 'border-emerald-800/50 bg-emerald-950/30 text-emerald-300' : 'border-red-900/50 bg-red-950/30 text-red-300'}`}>
          {notice.text}
        </p>
      )}

      <PageState loading={loading} error={error} onRetry={load}>
        {/* Stats */}
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[
            ['Monitored Locations', stats?.total_locations],
            ['Total Alerts', stats?.total_alerts],
            ['Predictions Recorded', stats?.total_predictions],
            ['Registered Users', stats?.total_users],
          ].map(([label, value]) => (
            <div key={label} className="card">
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">{label}</p>
              <p className="mt-2 text-2xl font-bold text-slate-100">{value ?? '—'}</p>
            </div>
          ))}
        </div>

        {/* Controls */}
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="card">
            <h3 className="mb-4 flex items-center gap-2 font-bold"><Zap className="h-5 w-5 text-brand" /> Model Operations</h3>
            <div className="space-y-3">
              <div className="flex items-center justify-between rounded-lg bg-surface-light p-3">
                <div>
                  <p className="text-sm font-semibold text-slate-200">Re-train Model</p>
                  <p className="text-xs text-slate-500">Re-train on the latest uploaded dataset</p>
                </div>
                <button disabled={busy} onClick={() => run('retrain')} className="btn-outline !py-1.5 text-xs">
                  <RefreshCw className={`h-3.5 w-3.5 ${busy === 'retrain' ? 'animate-spin' : ''}`} /> Re-train
                </button>
              </div>
              <div className="flex items-center justify-between rounded-lg bg-surface-light p-3">
                <div>
                  <p className="text-sm font-semibold text-slate-200">Trigger Prediction</p>
                  <p className="text-xs text-slate-500">Recompute risk for all monitored locations</p>
                </div>
                <button disabled={busy} onClick={() => run('trigger')} className="btn-outline !py-1.5 text-xs">
                  <Zap className={`h-3.5 w-3.5 ${busy === 'trigger' ? 'animate-pulse' : ''}`} /> Run Now
                </button>
              </div>
              <div className="flex items-center justify-between rounded-lg bg-surface-light p-3">
                <div>
                  <p className="text-sm font-semibold text-slate-200">Model Status</p>
                  <p className="text-xs text-slate-500">{stats?.model_loaded ? 'Model loaded and ready' : 'Model not loaded — using fallback'}</p>
                </div>
                <span className={`rounded-full px-2.5 py-1 text-[10px] font-bold ${stats?.model_loaded ? 'bg-emerald-500/10 text-emerald-400' : 'bg-amber-500/10 text-amber-400'}`}>
                  {stats?.model_loaded ? 'ACTIVE' : 'FALLBACK'}
                </span>
              </div>
            </div>
          </div>

          <div className="card">
            <h3 className="mb-4 flex items-center gap-2 font-bold"><Database className="h-5 w-5 text-accent" /> Dataset Management</h3>
            <p className="text-sm text-slate-400 mb-2">Upload a CSV to replace the historical dataset, then re-train.</p>
            <input
              type="file"
              accept=".csv"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              className="mb-3 w-full rounded-lg border border-slate-700 bg-surface-light px-3 py-2 text-xs text-slate-300 file:mr-3 file:rounded-md file:border-0 file:bg-slate-800 file:px-3 file:py-1.5 file:text-xs file:font-semibold file:text-slate-200"
            />
            <button disabled={!file || busy === 'upload'} onClick={upload} className="btn-primary w-full justify-center !py-2">
              <Upload className={`h-4 w-4 ${busy === 'upload' ? 'animate-pulse' : ''}`} /> Upload Dataset
            </button>
            <div className="mt-4 rounded-lg bg-surface-light p-3 text-xs text-slate-500">
              <SettingsIcon className="mr-1 inline h-3.5 w-3.5" />
              Data mode: <b className="text-slate-300">{stats?.data_mode}</b> · Weather API:{' '}
              <b className="text-slate-300">{settings?.weather_api_configured ? 'configured' : 'demo fallback'}</b>
            </div>
          </div>
        </div>

        {/* Recent alerts in admin */}
        <div className="card">
          <h3 className="mb-4 font-bold">All Alerts (Admin View)</h3>
          <div className="space-y-2">
            {alerts.slice(0, 8).map((a) => (
              <div key={a.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-surface-light px-3 py-2">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-slate-200">{a.location_name} — {a.risk_level}</p>
                  <p className="truncate text-[11px] text-slate-500">{a.message}</p>
                </div>
                <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${a.status === 'resolved' ? 'bg-emerald-500/10 text-emerald-400' : a.status === 'active' ? 'bg-red-500/10 text-red-400' : 'bg-sky-500/10 text-sky-400'}`}>
                  {a.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      </PageState>
    </div>
  )
}