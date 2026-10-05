import React, { useState } from 'react'
import RiskMap from '../components/RiskMap'
import RiskBadge from '../components/RiskBadge'
import DataSourceBadge from '../components/DataSourceBadge'
import { PageState } from '../components/States'
import { usePolling } from '../hooks/useApi'
import { CloudRain, Droplets, Thermometer, Wind, Mountain, MapPin, TrendingUp } from 'lucide-react'
import { riskMeta } from '../utils/risk'

export default function RiskMapPage() {
  const locs = usePolling('/api/locations', 20000)
  const [selected, setSelected] = useState(null)

  const locations = locs.data || []

  const handleSelect = (loc) => {
    setSelected(loc)
    if (window.innerWidth < 1024) {
      document.getElementById('detail-panel')?.scrollIntoView({ behavior: 'smooth' })
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold text-slate-100">Risk Map</h1>
          <p className="text-sm text-slate-400">Geospatial landslide risk across Northeast India</p>
        </div>
        <DataSourceBadge source={locations[0]?.environmental?.data_source || 'DEMO'} />
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
                <div className="card">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <h3 className="text-lg font-extrabold text-slate-100">{selected.name}</h3>
                      <p className="text-xs text-slate-400">
                        {selected.state} · {selected.district} · Lat {selected.latitude.toFixed(4)}, Lon {selected.longitude.toFixed(4)}
                      </p>
                    </div>
                    <RiskBadge level={selected.risk_level} score={selected.risk_score} />
                  </div>

                  <div className="mt-4 grid grid-cols-2 gap-3">
                    <div className="rounded-lg bg-surface-light p-3">
                      <div className="flex items-center gap-1.5 text-[11px] text-slate-400"><Mountain className="h-3.5 w-3.5" /> Slope</div>
                      <p className="mt-1 text-lg font-bold">{selected.slope}°</p>
                    </div>
                    <div className="rounded-lg bg-surface-light p-3">
                      <div className="flex items-center gap-1.5 text-[11px] text-slate-400"><TrendingUp className="h-3.5 w-3.5" /> Elevation</div>
                      <p className="mt-1 text-lg font-bold">{Math.round(selected.elevation)} m</p>
                    </div>
                    <div className="rounded-lg bg-surface-light p-3">
                      <div className="flex items-center gap-1.5 text-[11px] text-slate-400"><CloudRain className="h-3.5 w-3.5" /> Rainfall</div>
                      <p className="mt-1 text-lg font-bold">{selected.environmental?.rainfall ?? 0} mm/h</p>
                    </div>
                    <div className="rounded-lg bg-surface-light p-3">
                      <div className="flex items-center gap-1.5 text-[11px] text-slate-400"><Droplets className="h-3.5 w-3.5" /> Soil Moisture</div>
                      <p className="mt-1 text-lg font-bold">{selected.environmental?.soil_moisture ?? 0}%</p>
                    </div>
                    <div className="rounded-lg bg-surface-light p-3">
                      <div className="flex items-center gap-1.5 text-[11px] text-slate-400"><Thermometer className="h-3.5 w-3.5" /> Temperature</div>
                      <p className="mt-1 text-lg font-bold">{selected.environmental?.temperature ?? 0}°C</p>
                    </div>
                    <div className="rounded-lg bg-surface-light p-3">
                      <div className="flex items-center gap-1.5 text-[11px] text-slate-400"><Wind className="h-3.5 w-3.5" /> Humidity</div>
                      <p className="mt-1 text-lg font-bold">{selected.environmental?.humidity ?? 0}%</p>
                    </div>
                  </div>

                  <div className="mt-4">
                    <div className="flex items-center justify-between text-xs text-slate-400">
                      <span>Risk Score</span>
                      <span>{Math.round(selected.risk_score)} / 100</span>
                    </div>
                    <div className="mt-1 h-2.5 w-full overflow-hidden rounded-full bg-slate-800">
                      <div className="h-full rounded-full" style={{ width: `${selected.risk_score}%`, backgroundColor: riskMeta(selected.risk_level).color }} />
                    </div>
                  </div>

                  <div className="mt-3 flex items-center justify-between text-xs text-slate-400">
                    <span>Prediction Confidence</span>
                    <span className="font-bold text-slate-200">{Math.round(selected.confidence)}%</span>
                  </div>
                  <p className="mt-3 text-[11px] text-slate-500">
                    Last updated: {new Date(selected.last_updated || Date.now()).toLocaleString('en-IN')}
                  </p>
                </div>
              </>
            ) : (
              <div className="card flex flex-col items-center justify-center py-14 text-center text-slate-500">
                <MapPin className="mb-3 h-10 w-10" />
                <p className="text-sm">Click any marker on the map to see detailed location,
                  <br className="hidden xl:block" /> environmental and risk information.</p>
              </div>
            )}

            {/* Location list */}
            <div className="card">
              <h3 className="mb-3 font-bold">All Monitored Locations</h3>
              <div className="max-h-72 space-y-1.5 overflow-y-auto pr-1">
                {locations.map((loc) => (
                  <button
                    key={loc.id}
                    onClick={() => setSelected(loc)}
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