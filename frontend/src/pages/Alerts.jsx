import React, { useEffect, useState } from 'react'
import { Bell, CheckCheck, CircleCheck, Search, Filter } from 'lucide-react'
import api from '../services/api'
import RiskBadge from '../components/RiskBadge'
import { PageState } from '../components/States'
import { formatTs, NER_STATES } from '../utils/risk'

const LEVELS = ['', 'LOW', 'MODERATE', 'HIGH', 'CRITICAL']
const STATUSES = ['', 'active', 'acknowledged', 'resolved']

export default function Alerts() {
  const [alerts, setAlerts] = useState([])
  const [loading, setLoading] = useState(true)
  // Load failure = the list cannot be shown (PageState). Action failure = the
  // mutation did not apply, the list is still valid, so it must not replace it.
  const [error, setError] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [state, setState] = useState('')
  const [level, setLevel] = useState('')
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const [expanded, setExpanded] = useState(null)

  const load = async ({ silent = false } = {}) => {
    if (!silent) setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (state) params.set('state', state)
      if (level) params.set('risk_level', level)
      if (status) params.set('status', status)
      if (search) params.set('search', search)
      const res = await api.get(`/api/alerts?${params.toString()}`)
      setAlerts(res.data || [])
    } catch (e) {
      setError(e?.response?.data?.detail || e.message)
    } finally {
      if (!silent) setLoading(false)
    }
  }

  useEffect(() => {
    const t = setTimeout(load, 300)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, level, status, search])

  const updateStatus = async (id, newStatus) => {
    setActionError(null)
    try {
      await api.put(`/api/alerts/${id}`, { status: newStatus })
      // Refresh the table without bouncing the whole page back to a skeleton.
      await load({ silent: true })
    } catch (e) {
      setActionError(e?.response?.data?.detail || 'Could not update this alert')
    }
  }

  const counts = {
    active: alerts.filter((a) => a.status === 'active').length,
    critical: alerts.filter((a) => a.risk_level === 'CRITICAL').length,
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold text-slate-100">Alert Management</h1>
          <p className="text-sm text-slate-400">Early warning alerts issued by the risk engine</p>
        </div>
        <div className="flex gap-2">
          <span className="rounded-full bg-red-500/10 px-3 py-1.5 text-xs font-bold text-red-400">
            {counts.critical} critical
          </span>
          <span className="rounded-full bg-amber-500/10 px-3 py-1.5 text-xs font-bold text-amber-400">
            {counts.active} active
          </span>
        </div>
      </div>

      {actionError && (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-red-900/50 bg-red-950/30 px-4 py-2.5 text-sm text-red-300"
        >
          <span>{actionError} — the list below is unchanged.</span>
          <button type="button" className="btn-outline !py-1 text-xs" onClick={() => setActionError(null)}>
            Dismiss
          </button>
        </div>
      )}

      {/* Filters */}
      <div className="card grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <label className="label">Search Location</label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
            <input className="input !pl-9" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="e.g. Yuksom" />
          </div>
        </div>
        <div>
          <label className="label">State</label>
          <select className="input" value={state} onChange={(e) => setState(e.target.value)}>
            <option value="">All states</option>
            {NER_STATES.map((s) => <option key={s}>{s}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Risk Level</label>
          <select className="input" value={level} onChange={(e) => setLevel(e.target.value)}>
            {LEVELS.map((l) => <option key={l} value={l}>{l || 'All levels'}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Status</label>
          <select className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map((s) => <option key={s} value={s}>{s || 'All statuses'}</option>)}
          </select>
        </div>
      </div>

      <PageState loading={loading} error={error} onRetry={load}>
        {alerts.length === 0 ? (
          <div className="card flex flex-col items-center gap-3 py-16 text-slate-500">
            <Bell className="h-10 w-10" />
            <p className="text-sm">No alerts match the current filters.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {alerts.map((a) => (
              <div key={a.id} className="card !p-0">
                <div className="flex flex-col gap-3 p-5 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-surface-light">
                        <Bell className="h-4 w-4 text-red-400" />
                      </span>
                      <p className="font-bold text-slate-100">{a.location_name}</p>
                      <RiskBadge level={a.risk_level} score={a.risk_score} />
                      <span className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
                        a.status === 'resolved' ? 'bg-emerald-500/10 text-emerald-400'
                        : a.status === 'acknowledged' ? 'bg-sky-500/10 text-sky-400'
                        : 'bg-red-500/10 text-red-400'
                      }`}>{a.status}</span>
                    </div>
                    <p className="mt-2 text-sm text-slate-300">{a.message}</p>
                    <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-500">
                      <span>{a.location_state}</span>
                      <span>Alert #{a.id}</span>
                      <span>{formatTs(a.created_at)}</span>
                    </div>
                    {expanded === a.id && (
                      <div className="mt-3 rounded-lg border border-slate-700 bg-surface-light p-3">
                        <p className="text-xs font-bold uppercase tracking-wide text-slate-400 mb-2">Trigger Factors</p>
                        <div className="flex flex-wrap gap-1.5">
                          {(a.trigger_factors || []).map((f, i) => (
                            <span key={i} className="rounded-md bg-slate-800 px-2 py-1 text-[11px] text-slate-300">{f}</span>
                          ))}
                        </div>
                        {a.resolved_at && (
                          <p className="mt-2 text-[11px] text-slate-500">Resolved: {formatTs(a.resolved_at)}</p>
                        )}
                      </div>
                    )}
                  </div>
                  <div className="flex shrink-0 gap-2">
                    {(a.status === 'active' || a.status === 'acknowledged') && (
                      <button className="btn-outline !py-1.5 text-xs" onClick={() => setExpanded(expanded === a.id ? null : a.id)}>
                        View Details
                      </button>
                    )}
                    {a.status === 'active' && (
                      <button className="btn-outline !py-1.5 text-xs !text-sky-300" onClick={() => updateStatus(a.id, 'acknowledged')}>
                        <CheckCheck className="h-3.5 w-3.5" /> Acknowledge
                      </button>
                    )}
                    {a.status !== 'resolved' && (
                      <button className="btn-outline !py-1.5 text-xs !text-emerald-300" onClick={() => updateStatus(a.id, 'resolved')}>
                        <CircleCheck className="h-3.5 w-3.5" /> Resolve
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </PageState>
    </div>
  )
}