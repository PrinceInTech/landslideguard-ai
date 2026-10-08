import React, { useEffect, useRef, useState } from 'react'
import RiskMap from '../components/RiskMap'
import RiskBadge from '../components/RiskBadge'
import RiskBandRuler from '../components/RiskBandRuler'
import DataSourceBadge from '../components/DataSourceBadge'
import DataFreshness from '../components/DataFreshness'
import { PageState } from '../components/States'
import { useApi, usePolling } from '../hooks/useApi'
import { CloudRain, Droplets, Thermometer, Wind, Mountain, MapPin, TrendingUp, RefreshCw, Pause, Play, Info } from 'lucide-react'
import { formatTs } from '../utils/risk'

const CERTAINTY_HELP =
  'Derived from how far the model probability is from 0.5 (range 55–95). This is not calibrated statistical confidence.'

export default function RiskMapPage() {
  const [paused, setPaused] = useState(false)
  const locs = usePolling('/api/locations', 20000, [], { paused })
  // Same source of truth as the Dashboard header: the provider-level source,
  // not a per-row value defaulted to DEMO by this component.
  const summary = usePolling('/api/risk-summary', 20000, [], { paused })
  // Read-only context used by the detail panel: recorded alert triggers and
  // the most recent stored model outputs (probability / certainty).
  const alerts = useApi('/api/alerts')
  const predictions = useApi('/api/predictions')
  const [selected, setSelected] = useState(null)
  const detailRef = useRef(null)

  const locations = locs.data || []

  // Freshness is the newest API timestamp, not the browser clock.
  const riskAsOf = locations.reduce(
    (max, l) => (l.last_updated && l.last_updated > max ? l.last_updated : max),
    ''
  )

  // Keep the selected row in sync with the freshest polled payload so the
  // panel does not keep showing values from the moment of selection.
  useEffect(() => {
    if (!selected) return
    const fresh = locations.find((l) => l.id === selected.id)
    if (fresh && fresh !== selected) setSelected(fresh)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locations])

  const handleSelect = (loc) => {
    setSelected(loc)
    if (window.innerWidth < 1024) {
      const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches
      document.getElementById('detail-panel')?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth' })
    }
  }

  // Keyboard/AT users must land on the panel that just changed. Focusing from
  // an effect (after the panel is committed) is the only timing that reliably
  // has the element in the DOM.
  useEffect(() => {
    if (!selected) return
    detailRef.current?.focus({ preventScroll: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.id])

  const refreshAll = () => {
    locs.reload()
    summary.reload()
  }

  const latestAlertFor = (locationId) => {
    const rows = (Array.isArray(alerts.data) ? alerts.data : []).filter((a) => a.location_id === locationId)
    if (rows.length === 0) return null
    return [...rows].sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0))[0]
  }

  const latestPredictionFor = (locationId) => {
    const rows = (Array.isArray(predictions.data) ? predictions.data : []).filter(
      (p) => p.location_id === locationId
    )
    if (rows.length === 0) return null
    // /api/predictions is already ordered newest-first, but sort defensively.
    return [...rows].sort((a, b) => new Date(b.timestamp || 0) - new Date(a.timestamp || 0))[0]
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold text-slate-100">Risk Map</h1>
          <p className="text-sm text-slate-400">Geospatial landslide risk across Northeast India</p>
          <DataFreshness label="Risk data as of" timestamp={riskAsOf || null} />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={refreshAll}
            className="btn-outline !py-1.5 text-xs"
            aria-label="Refresh map data now"
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" /> Refresh
          </button>
          <button
            type="button"
            onClick={() => setPaused((p) => !p)}
            className="btn-outline !py-1.5 text-xs"
            aria-pressed={paused}
            aria-label={paused ? 'Resume auto-refresh' : 'Pause auto-refresh'}
          >
            {paused ? <Play className="h-3.5 w-3.5" aria-hidden="true" /> : <Pause className="h-3.5 w-3.5" aria-hidden="true" />}
            {paused ? 'Resume' : 'Pause'}
          </button>
          <DataSourceBadge
            source={summary.data?.data_source}
            degraded={summary.data?.live_degraded}
          />
        </div>
      </div>

      <PageState loading={locs.loading} error={locs.error} onRetry={locs.reload}>
        <div className="grid gap-4 xl:grid-cols-3">
          <div className="xl:col-span-2">
            <RiskMap locations={locations} onSelect={handleSelect} height="600px" />
          </div>

          {/* Detail panel */}
          <div className="space-y-4" id="detail-panel">
            {selected ? (
              <>
                <div
                  className="card"
                  ref={detailRef}
                  tabIndex={-1}
                  aria-label={`${selected.name} risk detail`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <h3 className="text-lg font-extrabold text-slate-100">{selected.name}</h3>
                      <p className="text-xs text-slate-400">
                        {selected.state} · {selected.district} · Lat {selected.latitude.toFixed(4)}, Lon {selected.longitude.toFixed(4)}
                      </p>
                    </div>
                    <RiskBadge level={selected.risk_level} score={selected.risk_score} />
                  </div>

                  {/* probability → score → level, with the published thresholds */}
                  <div className="mt-4">
                    <p className="mb-2 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-slate-400">
                      Model output
                      <Info
                        className="h-3.5 w-3.5 text-slate-500"
                        aria-hidden="true"
                        title="Probability is the Random Forest output; the score is 100 × p^1.6; the level comes from the published thresholds (docs/model.md)."
                      />
                    </p>
                    <RiskBandRuler
                      score={selected.risk_score}
                      level={selected.risk_level}
                      probability={
                        latestPredictionFor(selected.id)?.probability ?? null
                      }
                    />
                    <p className="mt-1.5 text-[11px] text-slate-500">
                      Probability shown only if a stored prediction exists for this site
                      {latestPredictionFor(selected.id)?.timestamp
                        ? ` (last recorded ${formatTs(latestPredictionFor(selected.id).timestamp)})`
                        : ' — none recorded yet'}.
                    </p>
                  </div>

                  {/* Model certainty — renamed from "confidence" on purpose. */}
                  <div
                    className="mt-3 flex items-center justify-between rounded-lg bg-surface-light px-3 py-2 text-xs text-slate-400"
                    title={CERTAINTY_HELP}
                  >
                    <span>Model certainty</span>
                    <span className="font-bold text-slate-200">
                      {Math.round(selected.confidence ?? 0)}%
                      <span className="ml-1 font-normal text-slate-500" aria-hidden="true">ⓘ</span>
                    </span>
                  </div>
                  <p className="mt-1 text-[11px] text-slate-500">{CERTAINTY_HELP}</p>

                  <div className="mt-4 grid grid-cols-2 gap-3">
                    <div className="rounded-lg bg-surface-light p-3">
                      <div className="flex items-center gap-1.5 text-[11px] text-slate-400"><Mountain className="h-3.5 w-3.5" aria-hidden="true" /> Slope</div>
                      <p className="mt-1 text-lg font-bold">{selected.slope}°</p>
                    </div>
                    <div className="rounded-lg bg-surface-light p-3">
                      <div className="flex items-center gap-1.5 text-[11px] text-slate-400"><TrendingUp className="h-3.5 w-3.5" aria-hidden="true" /> Elevation</div>
                      <p className="mt-1 text-lg font-bold">{Math.round(selected.elevation)} m</p>
                    </div>
                    <div className="rounded-lg bg-surface-light p-3">
                      <div className="flex items-center gap-1.5 text-[11px] text-slate-400"><CloudRain className="h-3.5 w-3.5" aria-hidden="true" /> Rainfall</div>
                      <p className="mt-1 text-lg font-bold">{selected.environmental?.rainfall ?? 0} mm/h</p>
                    </div>
                    <div className="rounded-lg bg-surface-light p-3">
                      <div className="flex items-center gap-1.5 text-[11px] text-slate-400"><Droplets className="h-3.5 w-3.5" aria-hidden="true" /> Soil Moisture</div>
                      <p className="mt-1 text-lg font-bold">{selected.environmental?.soil_moisture ?? 0}%</p>
                    </div>
                    <div className="rounded-lg bg-surface-light p-3">
                      <div className="flex items-center gap-1.5 text-[11px] text-slate-400"><Thermometer className="h-3.5 w-3.5" aria-hidden="true" /> Temperature</div>
                      <p className="mt-1 text-lg font-bold">{selected.environmental?.temperature ?? 0}°C</p>
                    </div>
                    <div className="rounded-lg bg-surface-light p-3">
                      <div className="flex items-center gap-1.5 text-[11px] text-slate-400"><Wind className="h-3.5 w-3.5" aria-hidden="true" /> Humidity</div>
                      <p className="mt-1 text-lg font-bold">{selected.environmental?.humidity ?? 0}%</p>
                    </div>
                  </div>

                  {/* Why this risk — only sources the read-only API supports. */}
                  <div className="mt-4">
                    <p className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-400">
                      Why this risk
                    </p>
                    {latestAlertFor(selected.id)?.trigger_factors?.length ? (
                      <>
                        <ul className="flex flex-wrap gap-1.5">
                          {latestAlertFor(selected.id).trigger_factors.map((f) => (
                            <li
                              key={f}
                              className="rounded-md border border-slate-700 bg-surface-light px-2 py-1 text-[11px] font-medium text-slate-300"
                            >
                              {f}
                            </li>
                          ))}
                        </ul>
                        <p className="mt-1.5 text-[11px] text-slate-500">
                          Trigger factors recorded by the risk engine when the latest alert was
                          issued ({formatTs(latestAlertFor(selected.id).created_at)}). The number
                          in brackets is that factor's contribution score at the time (0–100), not
                          a raw reading, and not a live per-prediction attribution.
                        </p>
                      </>
                    ) : (
                      <p className="rounded-lg border border-slate-700 bg-surface-light px-3 py-2.5 text-[11px] text-slate-500">
                        No alert has been issued for this site yet, so there are no recorded
                        trigger factors. Current conditions are shown above. Per-prediction
                        attribution needs a read-only explain endpoint (backend follow-up).
                      </p>
                    )}
                  </div>

                  <div className="mt-4 border-t border-slate-800 pt-3">
                    <DataFreshness
                      label="Location updated"
                      timestamp={selected.last_updated || null}
                    />
                  </div>
                </div>
              </>
            ) : (
              <div className="card flex flex-col items-center justify-center py-14 text-center text-slate-500">
                <MapPin className="mb-3 h-10 w-10" aria-hidden="true" />
                <p className="text-sm">Click any marker — or pick a site from the list below — to see
                  <br className="hidden xl:block" /> its risk, conditions and recorded triggers.</p>
              </div>
            )}

            {/* Location list */}
            <div className="card">
              <h3 className="mb-3 font-bold">All Monitored Locations</h3>
              <div className="max-h-72 space-y-1.5 overflow-y-auto pr-1">
                {locations.map((loc) => (
                  <button
                    key={loc.id}
                    type="button"
                    onClick={() => setSelected(loc)}
                    aria-current={selected?.id === loc.id ? 'true' : undefined}
                    className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left transition ${
                      selected?.id === loc.id ? 'bg-brand/10' : 'bg-surface-light/50 hover:bg-slate-800'
                    }`}
                  >
                    <div>
                      <p className="text-sm font-semibold text-slate-200">{loc.name}</p>
                      <p className="text-[11px] text-slate-500">{loc.state}</p>
                    </div>
                    <RiskBadge level={loc.risk_level} score={loc.risk_score} />
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      </PageState>
    </div>
  )
}
