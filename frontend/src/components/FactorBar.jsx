import React from 'react'

/**
 * Horizontal contribution bar for explainability.
 *
 * `display` picks the truthful label for the number being shown:
 *  - 'score' (default): a 0–100 contribution score reported by the API for one
 *    prediction run (see `_explain` in backend/app/ml/predictor.py).
 *  - 'share': a share of the model's total feature importance, in percent and
 *    summing to 100 across all features (ml/model/model_meta.json).
 *
 * `max` only scales the drawn bar so small-but-real values stay visible; it
 * never changes the number in the label.
 */
export default function FactorBar({ factor, contribution, max = 100, display = 'score' }) {
  const safe = Number.isFinite(contribution) ? contribution : 0
  const denominator = max > 0 ? max : 100
  const pct = Math.max(0, Math.min(100, (safe / denominator) * 100))
  // Colour follows the drawn magnitude in share mode (values are all < 20%)
  // and the raw 0–100 score otherwise.
  const basis = display === 'share' ? pct : safe
  const color = basis >= 75 ? '#ef4444' : basis >= 50 ? '#f97316' : basis >= 25 ? '#eab308' : '#22c55e'
  const label = display === 'share' ? `${safe.toFixed(1)}%` : `${safe.toFixed(0)} / 100`
  const labelTitle =
    display === 'share'
      ? 'Share of total feature importance from the trained model (all features sum to 100%)'
      : 'Contribution score for this prediction run (0 = baseline, 100 = fully in the risky range)'

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium text-slate-300">{factor}</span>
        <span className="text-slate-500" title={labelTitle}>
          {display === 'share' ? 'importance ' : 'contribution '}
          {label}
        </span>
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
