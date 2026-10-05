import React from 'react'
import { Database, Radio } from 'lucide-react'

export default function DataSourceBadge({ source }) {
  const isLive = source === 'LIVE'
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold ${
        isLive ? 'bg-emerald-500/15 text-emerald-400' : 'bg-amber-500/15 text-amber-400'
      }`}
    >
      {isLive ? <Radio className="h-3.5 w-3.5" /> : <Database className="h-3.5 w-3.5" />}
      {isLive ? 'LIVE DATA' : 'DEMO DATA'}
    </span>
  )
}