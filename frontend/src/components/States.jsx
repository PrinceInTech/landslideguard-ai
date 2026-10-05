import React from 'react'
import { AlertTriangle, XCircle } from 'lucide-react'

export function Loading({ label = 'Loading…' }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-slate-400">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-600 border-t-brand" />
      <p className="text-sm">{label}</p>
    </div>
  )
}

export function ErrorState({ message, onRetry }) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 rounded-xl border border-red-900/40 bg-red-950/20 px-6 py-12 text-center">
      <XCircle className="h-10 w-10 text-red-500" />
      <div>
        <p className="font-semibold text-red-300">Unable to load data</p>
        <p className="mt-1 text-sm text-slate-400">{message}</p>
      </div>
      {onRetry && (
        <button className="btn-outline" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  )
}

export function EmptyState({ message = 'No data available' }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10 text-slate-500">
      <AlertTriangle className="h-8 w-8" />
      <p className="text-sm">{message}</p>
    </div>
  )
}

export function PageState({ loading, error, onRetry, children, loadingLabel }) {
  if (loading) return <Loading label={loadingLabel} />
  if (error) return <ErrorState message={error} onRetry={onRetry} />
  return children
}