import React from 'react'
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet'
import L from 'leaflet'
import { riskMeta } from '../utils/risk'

const NER_CENTER = [26.2, 93.6]

// One divIcon per risk level, created once — not on every poll/render.
const ICON_CACHE = new Map()

function createIcon(level) {
  if (ICON_CACHE.has(level)) return ICON_CACHE.get(level)
  const color = riskMeta(level).color
  const svg = `
    <svg width="26" height="34" viewBox="0 0 26 34" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="${riskMeta(level).label} risk marker">
      <path d="M13 0C5.8 0 0 5.8 0 13c0 9.8 13 21 13 21s13-11.2 13-21C26 5.8 20.2 0 13 0z" fill="${color}" stroke="#0f172a" stroke-width="1.6"/>
      <circle cx="13" cy="13" r="5" fill="#0f172a"/>
    </svg>`
  const icon = L.divIcon({
    html: svg,
    className: '',
    iconSize: [26, 34],
    iconAnchor: [13, 34],
    popupAnchor: [0, -30],
  })
  ICON_CACHE.set(level, icon)
  return icon
}

export default function RiskMap({ locations, height = '520px', onSelect }) {
  return (
    <div className="relative" role="region" aria-label="Landslide risk map of Northeast India" style={{ height }}>
      <MapContainer
        center={NER_CENTER}
        zoom={6}
        scrollWheelZoom
        style={{ height: '100%', width: '100%', borderRadius: 12 }}
      >
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        />
        {locations.map((loc) => {
          const pos = [loc.latitude, loc.longitude]
          return (
            <Marker
              key={loc.id}
              position={pos}
              icon={createIcon(loc.risk_level)}
              title={`${loc.name} — ${loc.risk_level} (${Math.round(loc.risk_score)}/100)`}
              eventHandlers={{
                click: () => onSelect && onSelect(loc),
              }}
            >
              <Popup>
                <div className="text-slate-900 min-w-[190px]">
                  <p className="text-sm font-bold">{loc.name}</p>
                  <p className="text-xs text-slate-600">{loc.state} · {loc.district}</p>
                  <div className="mt-2 space-y-1 text-xs">
                    <p><b>Risk:</b> {loc.risk_level} ({Math.round(loc.risk_score)})</p>
                    <p title="Derived from how far the model probability is from 0.5 (range 55–95). Not calibrated confidence."><b>Model certainty:</b> {Math.round(loc.confidence)}%</p>
                    <p><b>Rainfall:</b> {loc.environmental?.rainfall ?? '—'} mm</p>
                    <p><b>Soil moisture:</b> {loc.environmental?.soil_moisture ?? '—'}%</p>
                    <p><b>Slope:</b> {loc.slope}° · <b>Elev:</b> {Math.round(loc.elevation)}m</p>
                  </div>
                </div>
              </Popup>
            </Marker>
          )
        })}
      </MapContainer>
      <MapLegend />
    </div>
  )
}

function MapLegend() {
  const items = ['LOW', 'MODERATE', 'HIGH', 'CRITICAL']
  return (
    <div
      className="pointer-events-none absolute right-3 top-3 z-[1000] rounded-lg border border-slate-700 bg-surface/90 px-3 py-2 text-xs backdrop-blur"
      role="img"
      aria-label="Risk legend: low, moderate, high and critical bands"
    >
      {items.map((lvl) => (
        <div key={lvl} className="flex items-center gap-2 py-0.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: riskMeta(lvl).color }} />
          <span className="font-medium text-slate-300">{riskMeta(lvl).label}</span>
        </div>
      ))}
    </div>
  )
}