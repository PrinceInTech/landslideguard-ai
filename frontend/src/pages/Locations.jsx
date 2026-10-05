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
  const [error, setError] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.get('/api/locations')
      setLocations(res.data || [])
    } catch (e) {
      setError(e?.response?.data?.detail || e.message)
    } finally {
      setLoading(false)
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
    setError(null)
    try {
      if (editing) {
        await api.put(`/api/locations/${editing.id}`, form)
      } else {
        await api.post('/api/locations', form)
      }
      setShowForm(false)
      load()
    } catch (err) {
      setError(err?.response?.data?.detail || 'Could not save location')
    } finally {
      setSaving(false)
    }
  }

  const remove = async (loc) => {
    if (!window.confirm(`Delete ${loc.name}?`)) return
    try {
      await api.delete(`/api/locations/${loc.id}`)
      load()
    } catch (e) {
      setError(e?.response?.data?.detail || 'Could not delete')
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

      {showForm && (
        <form onSubmit={save} className="card border-brand/30">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="font-bold">{editing ? `Edit ${editing.name}` : 'Add Monitoring Location'}</h3>
            <button type="button" onClick={() => setShowForm(false)} className="text-slate-400 hover:text-slate-200"><X className="h-5 w-5" /></button>
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
        <div className="overflow-x-auto rounded-xl border border-slate-800">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="bg-surface text-[11px] uppercase tracking-wider text-slate-500">
              <tr>
                <th className="px-4 py-3">Location</th>
                <th className="px-4 py-3">State</th>
                <th className="px-4 py-3">Lat</th>
                <th className="px-4 py-3">Lon</th>
                <th className="px-4 py-3">Slope</th>
                <th className="px-4 py-3">Elevation</th>
                <th className="px-4 py-3">Risk</th>
                <th className="px-4 py-3">Updated</th>
                <th className="px-4 py-3 text-right">Actions</th>
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
                      <button className="rounded p-1.5 text-slate-400 hover:bg-slate-800 hover:text-amber-400" title="Edit" onClick={() => openEdit(l)}>
                        <Pencil className="h-4 w-4" />
                      </button>
                      <button className="rounded p-1.5 text-slate-400 hover:bg-slate-800 hover:text-red-400" title="Delete" onClick={() => remove(l)}>
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </PageState>
    </div>
  )
}