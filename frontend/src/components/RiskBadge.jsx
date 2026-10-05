import React from 'react'
import { riskMeta } from '../utils/risk'

export function RiskBadge({ level, score, className = '' }) {
  const meta = riskMeta(level)
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-bold ${className}`}
      style={{ backgroundColor: meta.bg, color: meta.color, border: `1px solid ${meta.color}33` }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: meta.color }} />
      {level}
      {typeof score === 'number' && <span className="opacity-80">· {Math.round(score)}</span>}
    </span>
  )
}

export function RiskLevelDot({ level }) {
  const meta = riskMeta(level)
  return <span className="inline-block h-2.5 w-2.5 rounded-full animate-pulse-soft" style={{ backgroundColor: meta.color }} />
}

export default RiskBadge