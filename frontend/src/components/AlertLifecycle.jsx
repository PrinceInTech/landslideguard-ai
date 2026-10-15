import React from 'react'
import { Bell, CheckCheck, CircleCheck } from 'lucide-react'
import { formatTs } from '../utils/risk'

/**
 * Authority-facing lifecycle timeline for a single alert.
 *
 * Only timestamps the backend actually returns are rendered: `created_at`
 * (issued) and `resolved_at` (resolved). The API records acknowledgement as a
 * status change with no timestamp, so that step says so rather than inventing
 * a time. Nothing here is fabricated and no mutation is performed.
 */
const STAGES = [
  { key: 'created', label: 'Issued', Icon: Bell },
  { key: 'acknowledged', label: 'Acknowledged', Icon: CheckCheck },
  { key: 'resolved', label: 'Resolved', Icon: CircleCheck },
]

function isReached(status, key) {
  if (key === 'created') return true
  if (key === 'acknowledged') return status === 'acknowledged' || status === 'resolved'
  return status === 'resolved'
}

// The status "active" is represented by the "Issued" stage; the other two
// statuses share a name with their stage.
function currentStage(status) {
  return status === 'active' ? 'created' : status
}

export default function AlertLifecycle({ status, createdAt, resolvedAt, className = '' }) {
  return (
    <div className={className}>
      <p className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-400">Lifecycle</p>
      <ol aria-label="Alert lifecycle" className="space-y-2">
        {STAGES.map(({ key, label, Icon }) => {
          const reached = isReached(status, key)
          const current = currentStage(status) === key
          const timestamp = key === 'created' ? createdAt : key === 'resolved' ? resolvedAt : null
          return (
            <li
              key={key}
              aria-current={current ? 'step' : undefined}
              className={`flex flex-wrap items-center gap-x-2 text-xs ${
                reached ? 'text-slate-300' : 'text-slate-600'
              }`}
            >
              <Icon
                className={`h-3.5 w-3.5 shrink-0 ${reached ? 'text-brand' : 'text-slate-600'}`}
                aria-hidden="true"
              />
              <span className="font-semibold">{label}</span>
              {timestamp ? (
                <time dateTime={timestamp} className="text-slate-500">
                  {formatTs(timestamp)}
                </time>
              ) : reached && key === 'acknowledged' ? (
                <span className="text-slate-500">time not recorded</span>
              ) : null}
              {current && <span className="sr-only">(current status)</span>}
            </li>
          )
        })}
      </ol>
      {status === 'acknowledged' && (
        <p className="mt-2 text-[11px] text-slate-500">
          Acknowledgement is stored as a status only; this deployment does not record an
          acknowledgement timestamp.
        </p>
      )}
    </div>
  )
}
