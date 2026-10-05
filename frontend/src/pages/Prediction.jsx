import React, { useEffect, useState } from 'react'
import { BrainCircuit, PlayCircle, ShieldCheck, ListChecks } from 'lucide-react'
import api from '../services/api'
import RiskGauge from '../components/RiskGauge'
import FactorBar from '../components/FactorBar'
import RiskBadge from '../components/RiskBadge'
import { riskMeta } from '../utils/risk'

const LAND_COVERS = ['Dense Forest', 'Open Forest', 'Shrubland', 'Agriculture', 'Barren/Rocky']
const SOIL_TYPES = ['Clay Loam', 'Sandy Loam', 'Loam', 'Clay', 'Sandy Clay Loam']

const DEFAULTS = {
  location: 'Churachandpur',
  rainfall: 150,
  soil_moisture: 80,
  temperature: 24,
  humidity: 90,
  elevation: 914,
  slope: 32,
  land_cover: 'Dense Forest',
  soil_type: 'Clay Loam',
  rock_type: 'Mixed',
  historical_occurrence: 1,
}

export default function Prediction() {
  const [form, setForm] = useState(DEFAULTS)
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [locations, setLocations] = useState([])

  useEffect(() => {
    api.get('/api/locations').then((r) => setLocations(r.data || [])).catch(() => {})
  }, [])

  const set = (k) => (e) => {
    const v = e.target.value
    setForm((f) => ({ ...f, [k]: ['historical_occurrence', 'temperature', 'rainfall', 'soil_moisture', 'humidity', 'elevation', 'slope'].includes(k) ? Number(v) : v }))
  }

  const pickLocation = (name) => {
    const loc = locations.find((l) => l.name === name)
    if (loc) {
      setForm((f) => ({
        ...f,
        location: loc.name,
        elevation: loc.elevation,
        slope: loc.slope,
        rainfall: loc.environmental?.rainfall ?? f.rainfall,
        soil_moisture: loc.environmental?.soil_moisture ?? f.soil_moisture,
        temperature: loc.environmental?.temperature ?? f.temperature,
        humidity: loc.environmental?.humidity ?? f.humidity,
      }))
    }
  }

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const res = await api.post('/api/predict', form)
      setResult(res.data)
    } catch (err) {
      setError(err?.response?.data?.detail || 'Prediction failed')
      setResult(null)
    } finally {
      setBusy(false)
    }
  }

  const maxContrib = Math.max(1, ...(result?.contributing_factors || []).map((c) => c.contribution))

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold text-slate-100">AI Risk Prediction</h1>
        <p className="text-sm text-slate-400">
          Enter environmental conditions and run the trained ML model.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Input form */}
        <form onSubmit={submit} className="card space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="label">Location (optional)</label>
              <select className="input" value={form.location} onChange={set('location')}>
                <option value="">Custom input…</option>
                {locations.map((l) => (
                  <option key={l.id} value={l.name}>{l.name}, {l.state}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Preload location data</label>
              <button type="button" onClick={() => form.location && pickLocation(form.location)} className="btn-outline w-full justify-center">
                Load from monitor
              </button>
            </div>
            <div>
              <label className="label">Rainfall (mm)</label>
              <input className="input" type="number" min="0" max="500" value={form.rainfall} onChange={set('rainfall')} />
            </div>
            <div>
              <label className="label">Soil Moisture (%)</label>
              <input className="input" type="number" min="0" max="100" value={form.soil_moisture} onChange={set('soil_moisture')} />
            </div>
            <div>
              <label className="label">Temperature (°C)</label>
              <input className="input" type="number" value={form.temperature} onChange={set('temperature')} />
            </div>
            <div>
              <label className="label">Humidity (%)</label>
              <input className="input" type="number" min="0" max="100" value={form.humidity} onChange={set('humidity')} />
            </div>
            <div>
              <label className="label">Elevation (m)</label>
              <input className="input" type="number" min="0" max="9000" value={form.elevation} onChange={set('elevation')} />
            </div>
            <div>
              <label className="label">Slope (degrees)</label>
              <input className="input" type="number" min="0" max="90" value={form.slope} onChange={set('slope')} />
            </div>
            <div>
              <label className="label">Land Cover</label>
              <select className="input" value={form.land_cover} onChange={set('land_cover')}>
                {LAND_COVERS.map((l) => <option key={l}>{l}</option>)}
              </select>
            </div>
            <div>
              <label className="label">Soil Type</label>
              <select className="input" value={form.soil_type} onChange={set('soil_type')}>
                {SOIL_TYPES.map((l) => <option key={l}>{l}</option>)}
              </select>
            </div>
            <div>
              <label className="label">Historical Landslide</label>
              <select className="input" value={form.historical_occurrence} onChange={set('historical_occurrence')}>
                <option value={1}>Yes — occurred before</option>
                <option value={0}>No</option>
              </select>
            </div>
          </div>

          {error && (
            <p className="rounded-lg border border-red-900/40 bg-red-950/30 px-3 py-2 text-xs text-red-300">{error}</p>
          )}

          <button type="submit" disabled={busy} className="btn-primary w-full justify-center !py-3">
            {busy ? <><BrainCircuit className="h-5 w-5 animate-pulse" /> Predicting…</> : <><PlayCircle className="h-5 w-5" /> Predict Landslide Risk</>}
          </button>
        </form>

        {/* Results */}
        <div className="card">
          <h3 className="mb-4 font-bold">Prediction Result</h3>
          {!result ? (
            <div className="flex h-full min-h-[320px] flex-col items-center justify-center gap-3 text-center text-slate-500">
              <BrainCircuit className="h-12 w-12" />
              <p className="text-sm">The ML model output will appear here.</p>
            </div>
          ) : (
            <div className="space-y-5">
              <div className="flex flex-col items-center">
                <RiskGauge score={result.risk_score} level={result.risk_level} />
                <div className="mt-2 flex items-center gap-2">
                  <RiskBadge level={result.risk_level} score={result.risk_score} />
                  <span className="text-xs text-slate-400">Confidence {Math.round(result.confidence)}%</span>
                </div>
                <p className="mt-1 text-[11px] text-slate-500">
                  Probability: {(result.probability * 100).toFixed(1)}% · {result.model}
                </p>
              </div>

              <div className="rounded-lg border border-slate-700 bg-surface-light p-4">
                <p className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-slate-400">
                  <ShieldCheck className="h-4 w-4 text-accent" /> Top Risk Factors
                </p>
                <div className="space-y-3">
                  {result.contributing_factors.slice(0, 6).map((c) => (
                    <FactorBar key={c.factor} factor={c.factor} contribution={c.contribution} max={maxContrib} />
                  ))}
                </div>
              </div>

              <div className="rounded-lg border border-slate-700 bg-surface-light p-4">
                <p className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-slate-400">
                  <ListChecks className="h-4 w-4 text-accent" /> Recommended Actions
                </p>
                <ul className="space-y-1.5">
                  {result.recommended_actions.map((a, i) => (
                    <li key={i} className="flex gap-2 text-sm text-slate-300">
                      <span className="text-brand">•</span>{a}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}