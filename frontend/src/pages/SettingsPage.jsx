import React, { useEffect, useState } from 'react'
import { Settings as SettingsIcon, Server, Database, Cloud, Shield, Info } from 'lucide-react'
import api from '../services/api'
import { PageState } from '../components/States'

export default function SettingsPage() {
  const [health, setHealth] = useState(null)
  const [settings, setSettings] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const [h, s] = await Promise.all([api.get('/api/health'), api.get('/api/admin/settings')])
      setHealth(h.data)
      setSettings(s.data)
    } catch (e) {
      setError(e?.response?.data?.detail || e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold text-slate-100">System Settings</h1>
        <p className="text-sm text-slate-400">Configuration and health status of the platform</p>
      </div>

      <PageState loading={loading} error={error} onRetry={load}>
        <div className="card">
          <h3 className="mb-4 flex items-center gap-2 font-bold"><Server className="h-5 w-5 text-brand" /> Application Status</h3>
          <div className="grid gap-3 sm:grid-cols-2">
            {[
              ['Application', health?.app],
              ['Version', health?.version],
              ['API Status', health?.status],
              ['Database', health?.database],
            ].map(([k, v]) => (
              <div key={k} className="flex items-center justify-between rounded-lg bg-surface-light px-3 py-2.5">
                <span className="text-sm text-slate-400">{k}</span>
                <span className="font-semibold text-slate-100">{v}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <h3 className="mb-4 flex items-center gap-2 font-bold"><Database className="h-5 w-5 text-accent" /> Data & Model</h3>
          <div className="space-y-3">
            {[
              { icon: Cloud, label: 'Data Mode', value: settings?.data_mode },
              { icon: Database, label: 'Database', value: settings?.database || 'SQLite (backend/landslideguard.db)' },
              { icon: Info, label: 'Model Path', value: settings?.model_path },
              { icon: Shield, label: 'Weather API Key', value: settings?.weather_api_configured ? 'Configured (LIVE mode available)' : 'Not set (DEMO weather)' },
            ].map(({ icon: Icon, label, value }) => (
              <div key={label} className="flex items-center justify-between rounded-lg bg-surface-light px-3 py-2.5">
                <span className="flex items-center gap-2 text-sm text-slate-300"><Icon className="h-4 w-4 text-slate-500" /> {label}</span>
                <span className="text-xs font-semibold text-slate-200">{value}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <h3 className="mb-3 flex items-center gap-2 font-bold"><SettingsIcon className="h-5 w-5 text-emerald-400" /> Environment Variables</h3>
          <p className="text-sm text-slate-400">
            Configure via <code className="rounded bg-surface-light px-1.5 py-0.5 text-xs text-brand">.env</code> at the project root.
            See <code className="rounded bg-surface-light px-1.5 py-0.5 text-xs text-brand">.env.example</code> for the full list.
          </p>
          <div className="mt-3 space-y-1.5 rounded-lg bg-surface-light p-3 font-mono text-xs text-slate-400">
            <p>DATABASE_URL=sqlite:///backend/landslideguard.db</p>
            <p>DATA_MODE=DEMO</p>
            <p>OPENWEATHER_API_KEY= (optional, enables LIVE)</p>
            <p>JWT_SECRET=change-me-in-production</p>
          </div>
        </div>
      </PageState>
    </div>
  )
}