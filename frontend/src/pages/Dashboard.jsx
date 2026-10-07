import React from 'react'
import { Link } from 'react-router-dom'
import {
  MapPin,
  TrendingUp,
  Bell,
  ShieldAlert,
  CloudRain,
  Droplets,
  Thermometer,
  Activity,
  ArrowRight,
} from 'lucide-react'
import { usePolling } from '../hooks/useApi'
import api from '../services/api'
import StatCard from '../components/StatCard'
import RiskBadge from '../components/RiskBadge'
import DataSourceBadge from '../components/DataSourceBadge'
import { PageState, InlineError } from '../components/States'
import { riskMeta, formatTs } from '../utils/risk'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts'

export default function Dashboard() {
  const summary = usePolling('/api/risk-summary', 20000)
  const locations = usePolling('/api/locations', 20000)
  const alerts = usePolling('/api/alerts', 30000)

  // Three independent polls feed this page. Only gate the whole page while the
  // summary is still loading; otherwise each panel reports its own state so a
  // single failed endpoint cannot be mistaken for "zero alerts" or real values.
  if (summary.loading && !summary.data) {
    return <PageState loading />
  }

  const riskCounts = summary.data?.risk_counts || { LOW: 0, MODERATE: 0, HIGH: 0, CRITICAL: 0 }
  const riskColorClass = (level) =>
    ({ LOW: 'text-emerald-400', MODERATE: 'text-yellow-400', HIGH: 'text-orange-400', CRITICAL: 'text-red-400' })[level] || 'text-slate-100'
  const chartData = [
    { name: 'Low', value: riskCounts.LOW, fill: riskMeta('LOW').color },
    { name: 'Moderate', value: riskCounts.MODERATE, fill: riskMeta('MODERATE').color },
    { name: 'High', value: riskCounts.HIGH, fill: riskMeta('HIGH').color },
    { name: 'Critical', value: riskCounts.CRITICAL, fill: riskMeta('CRITICAL').color },
  ]

  // `usePolling` keeps the last good payload on a failed refresh, so an error
  // plus stale data would silently present old alerts as current. The list is
  // therefore only rendered while there is no error.
  const alertsFailed = Boolean(alerts.error)
  const alertsReady = Array.isArray(alerts.data)
  const activeAlerts = alertsReady ? alerts.data.filter((a) => a.status !== 'resolved') : []
  const criticalAlerts = activeAlerts.filter?.((a) => a.risk_level === 'CRITICAL') || []
  const env = locations.data?.[0]?.environmental || {}
  const highest = summary.data?.highest_risk_location

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold text-slate-100">Disaster Monitoring Dashboard</h1>
          <p className="text-sm text-slate-400">
            {/* Do not call DEMO readings "live": the badge below states the
                actual source. */}
            Risk overview — North Eastern Region · Viewed at {new Date().toLocaleString('en-IN')}
          </p>
        </div>
        <DataSourceBadge
          source={summary.data?.data_source}
          degraded={summary.data?.live_degraded}
        />
      </div>

      {/* Summary cards. On a failed refresh these would all render as zeros,
          which reads exactly like real data, so the error is shown instead. */}
      {summary.error ? (
        <InlineError
          label="Risk summary unavailable"
          message={summary.error}
          onRetry={summary.reload}
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard
            title="Monitored Locations"
            value={summary.data?.total_locations || 0}
            icon={MapPin}
            sub={`Across 8 NER states`}
          />
          <StatCard
            title="Current Overall Risk"
            value={summary.data?.overall_risk_level || '—'}
            icon={ShieldAlert}
            color={riskColorClass(summary.data?.overall_risk_level)}
            sub={`Avg score ${summary.data?.overall_avg_score ?? 0}`}
          />
          <StatCard
            title="Active Alerts"
            value={activeAlerts.length}
            icon={Bell}
            sub={`${criticalAlerts.length} critical`}
            color={criticalAlerts.length > 0 ? 'text-red-400' : 'text-slate-100'}
          />
          <StatCard
            title="Avg Model Confidence"
            value={`${summary.data?.avg_confidence ?? 0}%`}
            icon={TrendingUp}
            sub="Random Forest prediction"
          />
        </div>
      )}

      <PageState
        loading={summary.loading}
        error={summary.error}
        onRetry={summary.reload}
      >
        {/* Charts row */}
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="card lg:col-span-2">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="font-bold">Risk Distribution by Location</h3>
              <Link to="/analytics" className="flex items-center gap-1 text-xs font-medium text-brand hover:text-brand-light">
                Full analytics <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </div>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="name" stroke="#64748b" fontSize={12} />
                <YAxis stroke="#64748b" fontSize={12} allowDecimals={false} />
                <Tooltip
                  cursor={{ fill: 'rgba(148,163,184,0.06)' }}
                  contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                  labelStyle={{ color: '#e2e8f0' }}
                />
                <Bar dataKey="value" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Top risk location */}
          <div className="card">
            <h3 className="mb-4 font-bold">Highest Risk Location</h3>
            {highest ? (
              <div>
                <div className="rounded-lg border border-slate-700 bg-surface-light p-4">
                  <div className="flex items-center justify-between">
                    <p className="font-bold text-slate-100">{highest.name}</p>
                    <RiskBadge level={highest.risk_level} score={highest.risk_score} />
                  </div>
                  <p className="mt-1 text-xs text-slate-400">{highest.state}</p>
                  <div className="mt-4">
                    <div className="flex items-end gap-2">
                      <p className="text-4xl font-black" style={{ color: riskMeta(highest.risk_level).color }}>
                        {Math.round(highest.risk_score)}
                      </p>
                      <p className="pb-1 text-xs text-slate-500">/ 100 risk score</p>
                    </div>
                    <div className="mt-3 h-2.5 w-full overflow-hidden rounded-full bg-slate-800">
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${highest.risk_score}%`,
                          backgroundColor: riskMeta(highest.risk_level).color,
                        }}
                      />
                    </div>
                  </div>
                </div>
                <Link to="/map" className="btn-outline mt-4 w-full justify-center">
                  Open in Risk Map
                </Link>
              </div>
            ) : (
              <p className="text-sm text-slate-500">No data</p>
            )}
          </div>
        </div>

        {/* Environment + alerts row */}
        <div className="grid gap-4 lg:grid-cols-3">
          {/* Env conditions snapshot */}
          <div className="card lg:col-span-1">
            <h3 className="mb-4 font-bold">Environmental Snapshot</h3>
{locations.error ? (
              <InlineError message={locations.error} onRetry={locations.reload} />
            ) : !locations.data?.[0] ? (
              <p className="py-6 text-center text-sm text-slate-500">
                {locations.loading ? 'Loading…' : 'No location readings available'}
              </p>
            ) : (
              <div className="space-y-3">
                {[
                  { icon: CloudRain, label: 'Rainfall', value: `${env.rainfall ?? 0} mm/h` },
                  { icon: Droplets, label: 'Soil Moisture', value: `${env.soil_moisture ?? 0}%` },
                  { icon: Thermometer, label: 'Temperature', value: `${env.temperature ?? 0}°C` },
                  { icon: Activity, label: 'Humidity', value: `${env.humidity ?? 0}%` },
                ].map(({ icon: Icon, label, value }) => (
                  <div key={label} className="flex items-center justify-between rounded-lg bg-surface-light px-3 py-2.5">
                    <span className="flex items-center gap-2 text-sm text-slate-300">
                      <Icon className="h-4 w-4 text-accent" /> {label}
                    </span>
                    <span className="text-sm font-bold text-slate-100">{value}</span>
                  </div>
                ))}
                <p className="pt-1 text-[11px] text-slate-500">
                  Sample: {locations.data[0].name}, {locations.data[0].state}
                </p>
              </div>
            )}
          </div>

          {/* Recent alerts */}
          <div className="card lg:col-span-2">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="font-bold">Recent Alerts</h3>
              <Link to="/alerts" className="flex items-center gap-1 text-xs font-medium text-brand hover:text-brand-light">
                View all <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </div>
            {alertsFailed ? (
              <InlineError message={alerts.error} onRetry={alerts.reload} />
            ) : activeAlerts.length === 0 ? (
              <p className="py-6 text-center text-sm text-slate-500">
                {alertsReady ? 'No active alerts' : 'Loading…'}
              </p>
            ) : (
              <div className="space-y-3">
                {activeAlerts.slice(0, 5).map((a) => (
                  <div key={a.id} className="flex items-start justify-between gap-3 rounded-lg border border-slate-700/60 bg-surface-light px-4 py-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-sm font-bold text-slate-100">{a.location_name}</p>
                        <RiskBadge level={a.risk_level} score={a.risk_score} />
                      </div>
                      <p className="mt-1 truncate text-xs text-slate-400">{a.message}</p>
                      <p className="mt-1 text-[11px] text-slate-500">{formatTs(a.created_at)}</p>
                    </div>
                    <span className="shrink-0 rounded-full bg-slate-800 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-slate-400">
                      {a.status}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </PageState>
    </div>
  )
}
