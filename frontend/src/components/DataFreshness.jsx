import React, { useEffect, useState } from 'react'
import { Clock } from 'lucide-react'
import { formatTs, relativeAge } from '../utils/risk'

/**
 * Shows how old the data on screen actually is, using an API timestamp —
 * never the browser clock. Ticks internally so only this line re-renders
 * every second instead of the whole page.
 *
 * `timestamp` must come from the backend (`last_updated`, `created_at`, …).
 * When it is missing we say so rather than inventing a freshness value.
 */
export default function DataFreshness({ label, timestamp, className = '' }) {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])

  const age = relativeAge(timestamp, now)

  return (
    <p className={`flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-slate-400 ${className}`}>
      <Clock className="h-3.5 w-3.5 shrink-0 text-slate-500" aria-hidden="true" />
      {timestamp ? (
        <>
          <span>
            <span className="text-slate-500">{label}</span>{' '}
            <span className="font-semibold text-slate-300">{formatTs(timestamp)}</span>
          </span>
          <span aria-hidden="true" className="text-slate-600">·</span>
          <span className="text-slate-500">updated {age}</span>
          <span className="sr-only">, data last updated {formatTs(timestamp)}</span>
        </>
      ) : (
        <span className="text-slate-500">
          {label} <span className="font-semibold text-slate-400">timestamp unavailable</span>
        </span>
      )}
    </p>
  )
}
