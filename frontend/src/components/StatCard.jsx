import React from 'react'
import { ArrowDownRight, ArrowUpRight } from 'lucide-react'

export function StatCard({ title, value, sub, icon: Icon, trend, trendUp, color = 'text-slate-100' }) {
  return (
    <div className="card">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">{title}</p>
          <p className={`mt-2 text-2xl font-bold ${color}`}>{value}</p>
          {sub && <p className="mt-1 text-xs text-slate-500">{sub}</p>}
        </div>
        {Icon && (
          <div className="rounded-lg bg-surface-light p-2.5">
            <Icon className="h-5 w-5 text-brand" />
          </div>
        )}
      </div>
      {typeof trend === 'number' && (
        <div className={`mt-3 flex items-center gap-1 text-xs font-medium ${trendUp ? 'text-red-400' : 'text-slate-500'}`}>
          {trendUp ? <ArrowUpRight className="h-3.5 w-3.5" /> : <ArrowDownRight className="h-3.5 w-3.5" />}
          Trend {trend > 0 ? '+' : ''}{trend}%
        </div>
      )}
    </div>
  )
}

export default StatCard