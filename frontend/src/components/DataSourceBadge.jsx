import React from 'react'
import { Database, Radio, AlertTriangle } from 'lucide-react'

/**
 * Shows where the displayed readings actually came from.
 *
 * `source` must not be defaulted to DEMO by callers: an unknown source is
 * rendered as UNKNOWN so a failed request is never shown as demo data.
 * `degraded` marks the case where LIVE is configured but the last fetch failed
 * and fell back to simulated readings.
 */
export default function DataSourceBadge({ source, degraded = false }) {
  const label = !source
    ? 'SOURCE UNKNOWN'
    : degraded
      ? 'LIVE UNAVAILABLE — DEMO DATA'
      : source === 'LIVE'
        ? 'LIVE DATA'
        : 'DEMO DATA'

  const tone = !source
    ? 'bg-slate-500/15 text-slate-300'
    : degraded
      ? 'bg-red-500/15 text-red-400'
      : source === 'LIVE'
        ? 'bg-emerald-500/15 text-emerald-400'
        : 'bg-amber-500/15 text-amber-400'

  const Icon = !source ? AlertTriangle : degraded ? AlertTriangle : source === 'LIVE' ? Radio : Database

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold ${tone}`}
      title={
        degraded
          ? 'LIVE mode is configured but the weather API is not responding, so simulated readings are shown.'
          : undefined
      }
    >
      <Icon className="h-3.5 w-3.5" />
      {label}
    </span>
  )
}
