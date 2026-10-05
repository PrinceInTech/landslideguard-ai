import React from 'react'

/** Horizontal contribution bar for explainability. */
export default function FactorBar({ factor, value, contribution, max }) {
  const pct = max > 0 ? (contribution / max) * 100 : 0
  const color = contribution >= 75 ? '#ef4444' : contribution >= 50 ? '#f97316' : contribution >= 25 ? '#eab308' : '#22c55e'
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium text-slate-300">{factor}</span>
        <span className="text-slate-500">contrib. {contribution.toFixed(0)}%</span>
      </div>
      <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-800">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  )
}