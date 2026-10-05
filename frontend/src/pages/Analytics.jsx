import React from 'react'
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
} from 'recharts'
import { useApi } from '../hooks/useApi'
import { PageState } from '../components/States'
import StatCard from '../components/StatCard'
import RiskBadge from '../components/RiskBadge'
import { riskMeta } from '../utils/risk'
import { TrendingUp, CalendarDays, Linkedin, Mountain } from 'lucide-react'

const TOOLTIP_STYLE = { background: '#1e293b', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }
const AXIS_STYLE = { stroke: '#64748b', fontSize: 11 }
const GRID_STYLE = { stroke: '#1e293b' }

export default function Analytics() {
  const an = useApi('/api/analytics')

  const riskDist = (an.data?.risk_distribution || []).map((d) => ({
    ...d,
    name: d.level,
    fill: riskMeta(d.level).color,
  }))
  const monthly = an.data?.monthly_trends || []
  const states = an.data?.states || []
  const highRisk = an.data?.high_risk_locations || []
  const incidentsByState = an.data?.incidents_by_state || []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold text-slate-100">Historical Analytics</h1>
        <p className="text-sm text-slate-400">Trends and insights from historical landslide data (2018–2026, DEMO)</p>
      </div>

      <PageState loading={an.loading} error={an.error} onRetry={an.reload}>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard title="Rainfall–Landslide Correlation" value={an.data?.rainfall_correlation ?? 0} icon={Linkedin} sub="Pearson coefficient (demo data)" />
          <StatCard title="Total Incidents (History)" value={incidentsByState.reduce((s, i) => s + i.incidents, 0)} icon={Mountain} sub="Across historical dataset" />
          <StatCard title="Monthly Trend Window" value={monthly.length} icon={CalendarDays} sub="1 year of monthly aggregation" />
          <StatCard title="High Risk Locations" value={highRisk.filter((l) => ['HIGH', 'CRITICAL'].includes(l.risk_level)).length} icon={TrendingUp} sub="Currently monitored" color="#ef4444" />
        </div>

        {/* Monthly trends + rainfall */}
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="card">
            <h3 className="mb-4 font-bold">Monthly Landslide Incidents</h3>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={monthly}>
                <CartesianGrid strokeDasharray="3 3" {...GRID_STYLE} />
                <XAxis dataKey="month" {...AXIS_STYLE} />
                <YAxis {...AXIS_STYLE} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Bar dataKey="incidents" name="Incidents" fill="#f59e0b" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="card">
            <h3 className="mb-4 font-bold">Avg Rainfall vs Incidents</h3>
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={monthly}>
                <CartesianGrid strokeDasharray="3 3" {...GRID_STYLE} />
                <XAxis dataKey="month" {...AXIS_STYLE} />
                <YAxis {...AXIS_STYLE} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Legend />
                <Line type="monotone" dataKey="avg_rainfall" name="Avg rainfall (mm)" stroke="#38bdf8" strokeWidth={2} dot={{ r: 2 }} />
                <Line type="monotone" dataKey="incidents" name="Incidents" stroke="#f59e0b" strokeWidth={2} dot={{ r: 2 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Distribution + State risk */}
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="card">
            <h3 className="mb-4 font-bold">Current Risk Distribution</h3>
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie data={riskDist} dataKey="count" nameKey="name" innerRadius={55} outerRadius={90} paddingAngle={3} label>
                  {riskDist.map((d) => <Cell key={d.level} fill={d.fill} />)}
                </Pie>
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className="card">
            <h3 className="mb-4 font-bold">State-wise Risk Summary</h3>
            <div className="space-y-2.5">
              {states.map((s) => (
                <div key={s.state} className="flex items-center justify-between">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-slate-200">{s.state}</p>
                    <p className="text-[11px] text-slate-500">
                      {s.locations} locations · peak {s.highest_risk_location || '—'}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-bold" style={{ color: riskMeta(s.risk_level).color }}>
                      {s.avg_risk_score}
                    </span>
                    <RiskBadge level={s.risk_level} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* High risk list */}
        <div className="card">
          <h3 className="mb-4 font-bold">Highest Risk Locations</h3>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {highRisk.map((l) => (
              <div key={`${l.name}-${l.state}`} className="rounded-lg border border-slate-700 bg-surface-light p-4">
                <div className="flex items-center justify-between">
                  <p className="font-bold text-slate-100">{l.name}</p>
                  <RiskBadge level={l.risk_level} score={l.risk_score} />
                </div>
                <p className="mt-1 text-xs text-slate-400">{l.state} · {l.district}</p>
              </div>
            ))}
          </div>
        </div>
      </PageState>
    </div>
  )
}