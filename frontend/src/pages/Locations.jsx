import React, { useEffect, useState } from 'react'
import { MapPin, Plus, Pencil, Trash2, X } from 'lucide-react'
import api from '../services/api'
import RiskBadge from '../components/RiskBadge'
import { PageState } from '../components/States'
import { formatTs, NER_STATES } from '../utils/risk'

const EMPTY_FORM = { name: '', state: 'Assam', district: '', latitude: '', longitude: '', elevation: '', slope: '' }

export default function Locations() {
  const [locations, setLocations] = useState([])
  const [loading, setLoading] = useState(true)
  // Load failure vs save/delete failure: a rejected mutation must never wipe
  // the table that is still perfectly valid.
  const [error, setError] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)

  const load = async ({ silent = false } = {}) => {
    if (!silent) setLoading(true)
    setError(null)
    try {
      const res = await api.get('/api/locations')
      setLocations(res.data || [])
    } catch (e) {
      setError(e?.response?.data?.detail || e.message)
    } finally {
      if (!silent) setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const openCreate = () => {
    setEditing(null)
    setForm(EMPTY_FORM)
    setShowForm(true)
  }

  const openEdit = (loc) => {
    setEditing(loc)
    setForm({ ...loc })
    setShowForm(true)
  }

  const save = async (e) => {
    e.preventDefault()
    setSaving(true)
    setActionError(null)
    try {
      if (editing) {
        await api.put(`/api/locations/${editing.id}`, form)
      } else {
        await api.post('/api/locations', form)
      }
      setShowForm(false)
      await load({ silent: true })
    } catch (err) {
      setActionError(err?.response?.data?.detail || 'Could not save location')
    } finally {
      setSaving(false)
    }
  }

  const remove = async (loc) => {
    if (!window.confirm(`Delete ${loc.name}?`)) return
    setActionError(null)
    try {
      await api.delete(`/api/locations/${loc.id}`)
      await load({ silent: true })
    } catch (e) {
      setActionError(e?.response?.data?.detail || 'Could not delete this location')
    }
  }

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: ['latitude', 'longitude', 'elevation', 'slope'].includes(k) ? Number(e.target.value) : e.target.value }))

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold text-slate-100">Monitoring Locations</h1>
          <p className="text-sm text-slate-400">{locations.length} monitored sites across Northeast India</p>
        </div>
        <button className="btn-primary" onClick={openCreate}>
          <Plus className="h-4 w-4" /> Add Location
        </button>
      </div>

      {actionError && (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-red-900/50 bg-red-950/30 px-4 py-2.5 text-sm text-red-300"
        >
          <span>{actionError}</span>
          <button type="button" className="btn-outline !py-1 text-xs" onClick={() => setActionError(null)}>
            Dismiss
          </button>
        </div>
      )}

      {showForm && (
        <form onSubmit={save} className="card border-brand/30">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="font-bold">{editing ? `Edit ${editing.name}` : 'Add Monitoring Location'}</h3>
            <button type="button" onClick={() => setShowForm(false)} className="text-slate-400 hover:text-slate-200" aria-label="Close form"><X className="h-5 w-5" /></button>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <label className="label">Name</label>
              <input className="input" required value={form.name} onChange={set('name')} />
            </div>
            <div>
              <label className="label">State</label>
              <select className="input" value={form.state} onChange={set('state')}>
                {NER_STATES.map((s) => <option key={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <label className="label">District</label>
              <input className="input" required value={form.district} onChange={set('district')} />
            </div>
            <div>
              <label className="label">Latitude</label>
              <input className="input" type="number" step="0.0001" required value={form.latitude} onChange={set('latitude')} />
            </div>
            <div>
              <label className="label">Longitude</label>
              <input className="input" type="number" step="0.0001" required value={form.longitude} onChange={set('longitude')} />
            </div>
            <div>
              <label className="label">Elevation (m)</label>
              <input className="input" type="number" required value={form.elevation} onChange={set('elevation')} />
            </div>
            <div>
              <label className="label">Slope (°)</label>
              <input className="input" type="number" required value={form.slope} onChange={set('slope')} />
            </div>
            <div className="flex items-end">
              <button type="submit" disabled={saving} className="btn-primary w-full justify-center">
                {saving ? 'Saving…' : editing ? 'Update Location' : 'Add Location'}
              </button>
            </div>
          </div>
        </form>
      )}

      <PageState loading={loading} error={error} onRetry={load}>
        {locations.length === 0 ? (
          <div className="card flex flex-col items-center gap-3 py-16 text-center">
            <MapPin className="h-10 w-10 text-slate-600" aria-hidden="true" />
            <p className="font-bold text-slate-200">No monitoring locations yet</p>
            <p className="max-w-sm text-sm text-slate-400">
              Add a site to start tracking landslide risk on the map, dashboard and alerts.
            </p>
            <button className="btn-primary" onClick={openCreate}>
              <Plus className="h-4 w-4" aria-hidden="true" /> Add your first location
            </button>
          </div>
        ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-800">
          <table className="w-full min-w-[720px] text-left text-sm">
            <caption className="sr-only">Monitored locations with coordinates, terrain and current risk</caption>
            <thead className="bg-surface text-[11px] uppercase tracking-wider text-slate-500">
              <tr>
                <th scope="col" className="px-4 py-3">Location</th>
                <th scope="col" className="px-4 py-3">State</th>
                <th scope="col" className="px-4 py-3">Lat</th>
                <th scope="col" className="px-4 py-3">Lon</th>
                <th scope="col" className="px-4 py-3">Slope</th>
                <th scope="col" className="px-4 py-3">Elevation</th>
                <th scope="col" className="px-4 py-3">Risk</th>
                <th scope="col" className="px-4 py-3">Updated</th>
                <th scope="col" className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/70 bg-surface/40">
              {locations.map((l) => (
                <tr key={l.id} className="transition hover:bg-surface-light/50">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <MapPin className="h-4 w-4 text-brand" />
                      <span className="font-semibold text-slate-100">{l.name}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-slate-300">{l.state}</td>
                  <td className="px-4 py-3 text-slate-400">{l.latitude.toFixed(4)}</td>
                  <td className="px-4 py-3 text-slate-400">{l.longitude.toFixed(4)}</td>
                  <td className="px-4 py-3 text-slate-300">{l.slope}°</td>
                  <td className="px-4 py-3 text-slate-300">{Math.round(l.elevation)} m</td>
                  <td className="px-4 py-3"><RiskBadge level={l.risk_level} score={l.risk_score} /></td>
                  <td className="px-4 py-3 text-xs text-slate-500">{formatTs(l.last_updated)}</td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-1">
                      <button
                        className="rounded p-1.5 text-slate-400 hover:bg-slate-800 hover:text-amber-400"
                        title="Edit"
                        aria-label={`Edit ${l.name}`}
                        onClick={() => openEdit(l)}
                      >
                        <Pencil className="h-4 w-4" aria-hidden="true" />
                      </button>
                      <button
                        className="rounded p-1.5 text-slate-400 hover:bg-slate-800 hover:text-red-400"
                        title="Delete"
                        aria-label={`Delete ${l.name}`}
                        onClick={() => remove(l)}
                      >
                        <Trash2 className="h-4 w-4" aria-hidden="true" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        )}
      </PageState>
    </div>
  )
}