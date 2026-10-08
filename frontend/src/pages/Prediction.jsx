import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { BrainCircuit, PlayCircle, ShieldCheck, ListChecks, Eye, History, Info, AlertTriangle, Save } from 'lucide-react'
import api from '../services/api'
import RiskGauge from '../components/RiskGauge'
import FactorBar from '../components/FactorBar'
import RiskBadge from '../components/RiskBadge'
import RiskBandRuler from '../components/RiskBandRuler'
import { useApi } from '../hooks/useApi'
import { formatTs } from '../utils/risk'

const LAND_COVERS = ['Dense Forest', 'Open Forest', 'Shrubland', 'Agriculture', 'Barren/Rocky']
const SOIL_TYPES = ['Clay Loam', 'Sandy Loam', 'Loam', 'Clay', 'Sandy Clay Loam']
const NUMERIC_FIELDS = ['historical_occurrence', 'temperature', 'rainfall', 'soil_moisture', 'humidity', 'elevation', 'slope']

const CERTAINTY_HELP =
  'Derived from how far the model probability is from 0.5 (range 55–95). This is not calibrated statistical confidence.'

// location:'' (or null) is the API's read-only path: POST /api/predict only
// writes when a monitored site name matches, so an ad-hoc run never mutates.
const DEFAULTS = {
  location: '',
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
  // Which monitored site (if any) the last result was written to. null = preview.
  const [savedTo, setSavedTo] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [locations, setLocations] = useState([])

  const history = useApi('/api/predictions')

  useEffect(() => {
    api.get('/api/locations').then((r) => setLocations(r.data || [])).catch(() => {})
  }, [])

  const set = (k) => (e) => {
    const v = e.target.value
    setForm((f) => ({ ...f, [k]: NUMERIC_FIELDS.includes(k) ? Number(v) : v }))
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

  const writes = Boolean(form.location)
  const matchedSite = locations.find((l) => l.name === form.location) || null

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const payload = { ...form, location: form.location || null }
      const res = await api.post('/api/predict', payload)
      setResult(res.data)
      setSavedTo(matchedSite ? matchedSite.name : null)
      if (matchedSite) history.reload()
    } catch (err) {
      setError(err?.response?.data?.detail || 'Prediction failed')
      setResult(null)
      setSavedTo(null)
    } finally {
      setBusy(false)
    }
  }

  const nameById = new Map(locations.map((l) => [l.id, l.name]))
  const historyRows = (Array.isArray(history.data) ? history.data : []).slice(0, 8)

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
            <div className="sm:col-span-2">
              <label className="label" htmlFor="predict-location">
                Monitoring site
              </label>
              <select
                id="predict-location"
                className="input"
                value={form.location}
                onChange={set('location')}
                aria-describedby="predict-location-help"
              >
                <option value="">None — ad-hoc input (result is not saved)</option>
                {locations.map((l) => (
                  <option key={l.id} value={l.name}>
                    {l.name}, {l.state}
                  </option>
                ))}
              </select>
              <p id="predict-location-help" className="mt-1 text-[11px] text-slate-500">
                Choosing a site writes the result to that site's record. Choose "None" for a
                throwaway calculation.
              </p>
            </div>

            {matchedSite && (
              <div className="sm:col-span-2">
                <button
                  type="button"
                  onClick={() => pickLocation(form.location)}
                  className="btn-outline w-full justify-center"
                >
                  Load current conditions from monitor
                </button>
              </div>
            )}

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
            <div className="sm:col-span-2">
              <label className="label">Historical Landslide</label>
              <select className="input" value={form.historical_occurrence} onChange={set('historical_occurrence')}>
                <option value={1}>Yes — occurred before</option>
                <option value={0}>No</option>
              </select>
            </div>
          </div>

          {/* Write-back disclosure — shown before the action, not after it. */}
          {writes ? (
            <div className="flex gap-2 rounded-lg border border-amber-800/60 bg-amber-950/30 px-3 py-2.5 text-xs text-amber-300">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <p>
                Running with <b className="font-bold">{form.location}</b> selected will{' '}
                <b>update that monitored site's stored risk score, level and certainty</b> and may
                raise or resolve alerts. Use <b>"None"</b> for a preview that changes nothing.
              </p>
            </div>
          ) : (
            <div className="flex gap-2 rounded-lg border border-slate-700 bg-surface-light px-3 py-2.5 text-xs text-slate-400">
              <Eye className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <p>
                Preview mode — this run is read-only and is not written to any site record.
              </p>
            </div>
          )}

          {error && (
            <p className="rounded-lg border border-red-900/40 bg-red-950/30 px-3 py-2 text-xs text-red-300">{error}</p>
          )}

          <div className="space-y-2">
            <button type="submit" disabled={busy} className="btn-primary w-full justify-center !py-3">
              {busy ? (
                <><BrainCircuit className="h-5 w-5 animate-pulse" /> Predicting…</>
              ) : writes ? (
                <><Save className="h-5 w-5" /> Run prediction and update {form.location}</>
              ) : (
                <><PlayCircle className="h-5 w-5" /> Run prediction (preview, not saved)</>
              )}
            </button>
            {matchedSite && (
              <Link to="/map" className="btn-outline w-full justify-center">
                <Eye className="h-4 w-4" /> View monitored location on Risk Map
              </Link>
            )}
          </div>
        </form>

        {/* Results */}
        <div className="card" aria-live="polite">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-bold">Prediction Result</h3>
            {result && (
              <span
                className={`rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider ${
                  savedTo ? 'bg-amber-500/15 text-amber-300' : 'bg-slate-800 text-slate-400'
                }`}
              >
                {savedTo ? `Saved to ${savedTo}` : 'Preview only · not stored'}
              </span>
            )}
          </div>
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
                  <span className="text-xs text-slate-400" title={CERTAINTY_HELP}>
                    Model certainty {Math.round(result.confidence)}%
                  </span>
                </div>
                <p className="mt-1 text-[11px] text-slate-500" title={CERTAINTY_HELP}>
                  {CERTAINTY_HELP}
                </p>
                <p className="mt-1 text-[11px] text-slate-500">
                  Probability {(result.probability * 100).toFixed(1)}% · {result.model} · input data{' '}
                  <b className="text-slate-400">{result.data_source}</b>
                </p>
              </div>

              <RiskBandRuler score={result.risk_score} level={result.risk_level} probability={result.probability} />

              <div className="rounded-lg border border-slate-700 bg-surface-light p-4">
                <p className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-slate-400">
                  <ShieldCheck className="h-4 w-4 text-accent" /> Top Risk Factors
                </p>
                <div className="space-y-3">
                  {result.contributing_factors.slice(0, 6).map((c) => (
                    <FactorBar key={c.factor} factor={c.factor} contribution={c.contribution} max={100} />
                  ))}
                </div>
                <p className="mt-3 text-[11px] text-slate-500">
                  Contribution scores (0–100) reported by the model for this run — how far each
                  input sits in its risky range. Not a per-prediction decomposition of the forest
                  and not feature importance.
                </p>
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

      {/* Stored prediction history — read-only GET /api/predictions */}
      <div className="card">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="flex items-center gap-2 font-bold">
              <History className="h-5 w-5 text-brand" aria-hidden="true" /> Recent stored predictions
            </h3>
            <p className="text-[11px] text-slate-500">
              Read-only history recorded by the API (newest first). Rows created before this build
              may predate it.
            </p>
          </div>
          <button type="button" className="btn-outline !py-1.5 text-xs" onClick={history.reload}>
            Refresh
          </button>
        </div>
        {history.error ? (
          <p className="rounded-lg border border-red-900/40 bg-red-950/30 px-3 py-3 text-xs text-red-300">
            {history.error}
          </p>
        ) : historyRows.length === 0 ? (
          <p className="py-6 text-center text-sm text-slate-500">
            {history.loading ? 'Loading…' : 'No predictions stored yet.'}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-left text-sm">
              <caption className="sr-only">Most recent stored model predictions</caption>
              <thead className="text-[11px] uppercase tracking-wider text-slate-500">
                <tr>
                  <th scope="col" className="px-3 py-2">Site</th>
                  <th scope="col" className="px-3 py-2">Level</th>
                  <th scope="col" className="px-3 py-2">Score</th>
                  <th scope="col" className="px-3 py-2">Probability</th>
                  <th scope="col" className="px-3 py-2">Certainty</th>
                  <th scope="col" className="px-3 py-2">Recorded</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/70">
                {historyRows.map((p) => (
                  <tr key={p.id}>
                    <td className="px-3 py-2 font-semibold text-slate-200">
                      {nameById.get(p.location_id) || `Site #${p.location_id}`}
                    </td>
                    <td className="px-3 py-2"><RiskBadge level={p.risk_level} score={p.risk_score} /></td>
                    <td className="px-3 py-2 text-slate-300">{Math.round(p.risk_score)}</td>
                    <td className="px-3 py-2 text-slate-300">{(p.probability * 100).toFixed(1)}%</td>
                    <td className="px-3 py-2 text-slate-400" title={CERTAINTY_HELP}>
                      {Math.round(p.confidence)}%
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-500">{formatTs(p.timestamp)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-3 flex items-start gap-1.5 text-[11px] text-slate-500">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          Certainty is derived from how far the model probability is from 0.5 — it is not
          calibrated statistical confidence. Model card details are on the AI Insights page.
        </p>
      </div>
    </div>
  )
}
