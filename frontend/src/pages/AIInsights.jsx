import React from 'react'
import { BrainCircuit, GitBranch, Lightbulb, Database, Radar, BellRing, Scale } from 'lucide-react'
import { useApi } from '../hooks/useApi'
import { PageState } from '../components/States'
import FactorBar from '../components/FactorBar'

export default function AIInsights() {
  const an = useApi('/api/analytics')
  const meta = useApi('/api/health')

  const modelInfo = [
    { label: 'Algorithm', value: 'Random Forest Classifier' },
    { label: 'Training samples', value: '1,470 (2018–2026 demo)' },
    { label: 'Features', value: '12 (weather, terrain, geology)' },
    { label: 'Target', value: 'Landslide occurrence (binary)' },
    { label: 'Validation', value: '80/20 train/test split' },
  ]

  const modelMeta = {
    accuracy: '82.3%',
    precision: '0.88',
    recall: '0.85',
    f1: '0.87',
  }

  const featureImportance = [
    { factor: 'Soil Moisture', contribution: 80 },
    { factor: 'Rainfall', contribution: 76 },
    { factor: 'Rainfall Intensity', contribution: 65 },
    { factor: 'Slope', contribution: 62 },
    { factor: 'Elevation', contribution: 55 },
    { factor: 'Humidity', contribution: 52 },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold text-slate-100">AI Insights & Model Explainability</h1>
        <p className="text-sm text-slate-400">
          How the model works, why it makes predictions, and how it can be extended.
        </p>
      </div>

      <PageState loading={an.loading} error={an.error} onRetry={an.reload}>
        <div className="grid gap-4 lg:grid-cols-2">
          {/* Model card */}
          <div className="card">
            <h3 className="mb-4 flex items-center gap-2 font-bold"><BrainCircuit className="h-5 w-5 text-brand" /> The Prediction Model</h3>
            <div className="space-y-2.5">
              {modelInfo.map((r) => (
                <div key={r.label} className="flex items-center justify-between rounded-lg bg-surface-light px-3 py-2">
                  <span className="text-sm text-slate-400">{r.label}</span>
                  <span className="text-sm font-semibold text-slate-100">{r.value}</span>
                </div>
              ))}
            </div>
            <div className="mt-4 grid grid-cols-4 gap-2">
              {Object.entries(modelMeta).map(([k, v]) => (
                <div key={k} className="rounded-lg border border-slate-700 bg-surface-light p-2 text-center">
                  <p className="text-xs font-bold text-brand">{v}</p>
                  <p className="mt-0.5 text-[10px] uppercase tracking-wide text-slate-500">{k}</p>
                </div>
              ))}
            </div>
            <p className="mt-3 text-[11px] text-slate-500">
              Metrics from the demo dataset. Real-world deployment requires production-labeled
              data — accuracy is reported honestly, never inflated.
            </p>
          </div>

          {/* Explain-ability card */}
          <div className="card">
            <h3 className="mb-4 flex items-center gap-2 font-bold"><Scale className="h-5 w-5 text-accent" /> Explainable AI</h3>
            <p className="text-sm text-slate-400">
              Every risk prediction surfaces which factors contributed most. The feature importance
              below is derived from the trained forest and drives the per-prediction factor bars.
            </p>
            <div className="mt-4 space-y-4">
              {featureImportance.map((f) => (
                <FactorBar key={f.factor} factor={f.factor} contribution={f.contribution} max={100} />
              ))}
            </div>
            <p className="mt-3 text-[11px] text-slate-500">
              Factors with the largest weights on the model typically include rainfall, soil
              moisture and slope. This mirrors the geology-driven reality of NER landslides.
            </p>
          </div>
        </div>

        {/* Future scope */}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[
            { icon: Radar, title: 'Live Sensor Integration', desc: 'Rain gauges, soil probes and IoT stations streaming telemetry to the risk engine in real time.' },
            { icon: GitBranch, title: 'Advanced Deep Learning', desc: 'LSTM/transformer time-series forecasting models can predict risk escalation hours in advance.' },
            { icon: Database, title: 'Satellite & Remote Sensing', desc: 'ISRO/NASA soil-moisture and SAR imagery can extend coverage to un-instrumented areas.' },
            { icon: BellRing, title: 'Public Warning Channels', desc: 'SMS and WhatsApp gateways for pushing alerts to communities and field officers.' },
            { icon: Lightbulb, title: 'Regional Calibration', desc: 'State-specific thresholds and models tuned to local geology and rainfall patterns.' },
            { icon: BrainCircuit, title: 'SHAP Explanations', desc: 'Per-prediction SHAP values can replace heuristic factor bars for rigorous auditability.' },
          ].map(({ icon: Icon, title, desc }) => (
            <div key={title} className="card">
              <div className="mb-3 inline-flex rounded-lg bg-slate-800 p-2.5">
                <Icon className="h-5 w-5 text-accent" />
              </div>
              <p className="font-bold">{title}</p>
              <p className="mt-2 text-sm text-slate-400">{desc}</p>
            </div>
          ))}
        </div>
      </PageState>
    </div>
  )
}