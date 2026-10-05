import React from 'react'
import { riskMeta } from '../utils/risk'

/** Semi-circular risk gauge rendered as SVG. */
export default function RiskGauge({ score, level, size = 220 }) {
  const meta = riskMeta(level)
  const radius = (size - 40) / 2
  const stroke = 18
  const circumference = Math.PI * radius
  const filled = Math.max(0, Math.min(100, score)) / 100

  const cx = size / 2
  const cy = size / 2 + 10

  return (
    <div className="flex flex-col items-center">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* Track */}
        <path
          d={`M ${cx - radius} ${cy} A ${radius} ${radius} 0 0 1 ${cx + radius} ${cy}`}
          fill="none"
          stroke="#334155"
          strokeWidth={stroke}
          strokeLinecap="round"
        />
        {/* Filled */}
        <path
          d={`M ${cx - radius} ${cy} A ${radius} ${radius} 0 0 1 ${cx + radius} ${cy}`}
          fill="none"
          stroke={meta.color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${circumference}`}
          strokeDashoffset={`${circumference * (1 - filled)}`}
        />
        {/* Ticks */}
        {[0, 30, 60, 80, 100].map((t) => {
          const angle = Math.PI - (t / 100) * Math.PI
          const x1 = cx + radius * Math.cos(angle)
          const y1 = cy - radius * Math.sin(angle)
          const x2 = cx + (radius - 10) * Math.cos(angle)
          const y2 = cy - (radius - 10) * Math.sin(angle)
          return <line key={t} x1={x1} y1={y1} x2={x2} y2={y2} stroke="#475569" strokeWidth={2} />
        })}
        <text x={cx} y={cy - 6} textAnchor="middle" fill="#f8fafc" fontSize="38" fontWeight="800">
          {Math.round(score)}
        </text>
        <text x={cx} y={cy + 26} textAnchor="middle" fill={meta.color} fontSize="14" fontWeight="700" letterSpacing="1">
          {level}
        </text>
      </svg>
      <div className="mt-1 flex w-full justify-between px-4 text-[10px] font-medium text-slate-500">
        <span>Low</span>
        <span>Moderate</span>
        <span>High</span>
        <span>Critical</span>
      </div>
    </div>
  )
}