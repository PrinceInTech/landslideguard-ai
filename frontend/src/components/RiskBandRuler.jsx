import React from 'react'
import { riskMeta, RISK_THRESHOLDS, bandForScore } from '../utils/risk'

/**
 * Visualises the project's documented decision pipeline
 * (docs/model.md: `risk_score = 100 * probability^1.6`, then the inclusive
 * thresholds in backend/app/risk.py):
 *
 *   model probability  →  risk score  →  risk level
 *
 * The backend is still the authority that assigns the level; this component
 * only restates the values it was given alongside the published thresholds.
 */
export default function RiskBandRuler({ score, level, probability }) {
  const numericScore = Number(score)
  const hasScore = Number.isFinite(numericScore)
  const shownLevel = level || (hasScore ? bandForScore(numericScore) : null)

  const steps = []
  steps.push({
    label: 'Model probability',
    value: probability === null || probability === undefined
      ? 'not recorded'
      : `${(Number(probability) * 100).toFixed(1)}%`,
    hint: 'Random Forest output',
  })
  steps.push({
    label: 'Risk score',
    value: hasScore ? `${numericScore.toFixed(1)} / 100` : '—',
    hint: 'score = 100 × p^1.6',
  })
  steps.push({
    label: 'Risk level',
    value: shownLevel || '—',
    hint: 'threshold classification',
    color: shownLevel ? riskMeta(shownLevel).color : undefined,
  })

  return (
    <div className="space-y-3">
      {/* probability → score → level */}
      <ol className="flex flex-col gap-2 sm:flex-row sm:items-stretch" aria-label="How the risk level is derived">
        {steps.map((s, i) => (
          <li key={s.label} className="flex flex-1 items-center gap-2">
            <div className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-surface-light px-3 py-2">
              <p className="text-[10px] font-bold uppercase tracking-wide text-slate-500">{s.label}</p>
              <p className="mt-0.5 truncate text-sm font-extrabold" style={s.color ? { color: s.color } : undefined}>
                {s.value}
              </p>
              <p className="text-[10px] text-slate-500">{s.hint}</p>
            </div>
            {i < steps.length - 1 && (
              <span aria-hidden="true" className="shrink-0 text-slate-600 max-sm:rotate-90 max-sm:self-center">
                →
              </span>
            )}
          </li>
        ))}
      </ol>

      {/* Threshold bands */}
      <div>
        <div
          className="relative h-3 w-full overflow-visible rounded-full"
          role="img"
          aria-label={
            hasScore
              ? `Risk score ${numericScore.toFixed(0)} out of 100, in the ${shownLevel} band`
              : 'Risk band scale'
          }
        >
          <div className="flex h-full w-full overflow-hidden rounded-full">
            {RISK_THRESHOLDS.map((band, i) => {
              const lower = i === 0 ? 0 : RISK_THRESHOLDS[i - 1].upper
              const width = band.upper - lower
              return (
                <div
                  key={band.level}
                  style={{
                    width: `${width}%`,
                    backgroundColor: riskMeta(band.level).color,
                    opacity: shownLevel === band.level ? 0.95 : 0.3,
                  }}
                />
              )
            })}
          </div>
          {hasScore && (
            <div
              className="absolute -top-1 h-5 w-0.5 rounded-full bg-slate-100 shadow"
              style={{ left: `calc(${Math.min(100, Math.max(0, numericScore))}% - 1px)` }}
            >
              <span
                className="absolute -top-1 left-1/2 h-2 w-2 -translate-x-1/2 rotate-45 rounded-[1px] bg-slate-100"
                aria-hidden="true"
              />
            </div>
          )}
        </div>
        <div className="mt-1.5 flex text-[10px] font-semibold text-slate-500">
          {RISK_THRESHOLDS.map((band, i) => {
            const lower = i === 0 ? 0 : RISK_THRESHOLDS[i - 1].upper
            const width = band.upper - lower
            return (
              <span
                key={band.level}
                style={{ width: `${width}%` }}
                className={`truncate ${shownLevel === band.level ? 'text-slate-300' : ''} ${
                  i === 0 ? 'text-left' : i === RISK_THRESHOLDS.length - 1 ? 'text-right' : 'text-center'
                }`}
              >
                {band.level} ≤{band.upper}
              </span>
            )
          })}
        </div>
      </div>
    </div>
  )
}
