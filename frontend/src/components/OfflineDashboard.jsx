import React from 'react'
import { MapPin, ShieldAlert, TrendingUp, Bell, WifiOff } from 'lucide-react'
import StatCard from './StatCard'
import RiskBadge from './RiskBadge'
import DataSourceBadge from './DataSourceBadge'
import { formatTs } from '../utils/risk'

/**
 * Read-only fallback for when the browser is offline and only a previously
 * cached dashboard summary is available.
 *
 * It renders ONLY the aggregate summary that `services/offlineCache` is allowed
 * to persist — never alerts, the location list, predictions, credentials or
 * admin data — and it is always visibly labelled STALE / LAST UPDATED so a
 * cached snapshot can never be mistaken for live data.
 */
export function OfflineDashboard({ cached }) {
  const summary = cached?.summary
  if (!summary) return null

  const riskCounts = summary.risk_counts || { LOW: 0, MODERATE: 0, HIGH: 0, CRITICAL: 0 }
  const highest = summary.highest_risk_location

  return (
    <div className="space-y-6">
      <div role="status" className="rounded-xl border border-amber-800/60 bg-amber-950/30 px-4 py-3">
        <p className="flex items-center gap-2 font-bold text-amber-200">
          <WifiOff className="h-4 w-4" aria-hidden="true" /> OFFLINE — STALE / LAST UPDATED DATA
        </p>
        <p className="mt-1 text-xs text-amber-300/90">
          Saved {formatTs(cached.saved_at)}. This is a read-only snapshot. Live risk data,
          predictions and alerts require a backend connection and are not available offline.
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-amber-500/15 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-amber-300">
            STALE · LAST UPDATED {formatTs(cached.saved_at)}
          </span>
          <DataSourceBadge source={summary.data_source} degraded={summary.live_degraded} />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          title="Monitored Locations"
          value={summary.total_locations}
          icon={MapPin}
          sub="Last known snapshot"
        />
        <StatCard
          title="Current Overall Risk"
          value={summary.overall_risk_level || '—'}
          icon={ShieldAlert}
          sub={`Avg score ${summary.overall_avg_score ?? 0}`}
        />
        <StatCard
          title="Critical Zones"
          value={riskCounts.CRITICAL}
          icon={Bell}
          sub={`${riskCounts.HIGH} high · ${riskCounts.MODERATE} moderate`}
          color={riskCounts.CRITICAL > 0 ? 'text-red-400' : 'text-slate-100'}
        />
        <StatCard
          title="Avg Model Certainty"
          value={`${summary.avg_confidence ?? 0}%`}
          icon={TrendingUp}
          sub="Random Forest · not calibrated confidence"
        />
      </div>

      <div className="card">
        <h3 className="mb-4 font-bold">Highest Risk Location (last known)</h3>
        {highest ? (
          <div className="rounded-lg border border-slate-700 bg-surface-light p-4">
            <div className="flex items-center justify-between">
              <p className="font-bold text-slate-100">{highest.name}</p>
              <RiskBadge level={highest.risk_level} score={highest.risk_score} />
            </div>
            <p className="mt-1 text-xs text-slate-400">{highest.state}</p>
          </div>
        ) : (
          <p className="text-sm text-slate-500">No cached location detail.</p>
        )}
        <p className="mt-4 text-xs text-slate-500">
          The live dashboard, risk map and alerts reconnect automatically when the browser is
          back online.
        </p>
      </div>
    </div>
  )
}

export default OfflineDashboard
