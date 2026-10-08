import React from 'react'
import { BrainCircuit, GitBranch, Lightbulb, Database, Radar, BellRing, Scale, Info } from 'lucide-react'
import FactorBar from '../components/FactorBar'

/**
 * Static copy of ml/model/model_meta.json.
 *
 * The frontend Docker build context is `frontend/` only, so this file cannot
 * import the JSON directly (that would build in dev/CI and break in Docker).
 * The API also exposes no read-only model-metadata endpoint. Sync manually
 * whenever the model is retrained:
 *   version, trained_at_utc, accuracy/precision/recall/f1, n_samples,
 *   n_features, feature_importance, label_leakage.
 */
const MODEL_CARD = {
  version: '1.1.0',
  trainedAt: '2026-10-05T17:49:07 UTC',
  algorithm: 'Random Forest Classifier (scikit-learn 1.9.1)',
  hyperparameters: 'n_estimators=200 · class_weight=balanced · random_state=42',
  samples: '1,470 (1,176 train / 294 test, stratified 80/20)',
  features: '12 (weather, terrain, geology, history)',
  target: 'Landslide occurrence (binary)',
  trainedOn: 'DEMO / sample dataset — not production data',
}

const METRICS = [
  { key: 'accuracy', value: '82.3%' },
  { key: 'precision', value: '0.88' },
  { key: 'recall', value: '0.85' },
  { key: 'f1', value: '0.87' },
]

// feature_importance from ml/model/model_meta.json, expressed as % of total.
// All 12 values sum to 100.
const FEATURE_IMPORTANCE = [
  { key: 'soil_moisture', label: 'Soil Moisture', share: 17.97 },
  { key: 'rainfall', label: 'Rainfall', share: 16.99 },
  { key: 'rainfall_intensity', label: 'Rainfall Intensity', share: 13.4 },
  { key: 'slope', label: 'Slope', share: 12.88 },
  { key: 'elevation', label: 'Elevation', share: 10.14 },
  { key: 'humidity', label: 'Humidity', share: 9.92 },
  { key: 'temperature', label: 'Temperature', share: 5.13 },
  { key: 'distance_to_drain', label: 'Distance to Drain', share: 4.26 },
  { key: 'historical_occurrence', label: 'Historical Occurrence', share: 4.0 },
  { key: 'soil_type_enc', label: 'Soil Type', share: 1.86 },
  { key: 'land_cover_enc', label: 'Land Cover', share: 1.86 },
  { key: 'rock_type_enc', label: 'Rock Type', share: 1.59 },
]
const TOP_SHARE = Math.max(...FEATURE_IMPORTANCE.map((f) => f.share))

export default function AIInsights() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold text-slate-100">AI Insights & Model Explainability</h1>
        <p className="text-sm text-slate-400">
          How the model works, what it was trained on, and what it can and cannot tell you.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Model card */}
        <div className="card">
          <h3 className="mb-4 flex items-center gap-2 font-bold">
            <BrainCircuit className="h-5 w-5 text-brand" /> The Prediction Model
          </h3>
          <div className="space-y-2.5">
            {[
              { label: 'Algorithm', value: MODEL_CARD.algorithm },
              { label: 'Version', value: MODEL_CARD.version },
              { label: 'Trained at', value: MODEL_CARD.trainedAt },
              { label: 'Training samples', value: MODEL_CARD.samples },
              { label: 'Features', value: MODEL_CARD.features },
              { label: 'Target', value: MODEL_CARD.target },
              { label: 'Hyperparameters', value: MODEL_CARD.hyperparameters },
              { label: 'Trained on', value: MODEL_CARD.trainedOn },
            ].map((r) => (
              <div key={r.label} className="flex items-center justify-between gap-4 rounded-lg bg-surface-light px-3 py-2">
                <span className="shrink-0 text-sm text-slate-400">{r.label}</span>
                <span className="text-right text-sm font-semibold text-slate-100">{r.value}</span>
              </div>
            ))}
          </div>
          <div className="mt-4 grid grid-cols-4 gap-2">
            {METRICS.map((m) => (
              <div key={m.key} className="rounded-lg border border-slate-700 bg-surface-light p-2 text-center">
                <p className="text-xs font-bold text-brand">{m.value}</p>
                <p className="mt-0.5 text-[10px] uppercase tracking-wide text-slate-500">{m.key}</p>
              </div>
            ))}
          </div>
          <p className="mt-3 text-[11px] text-slate-500">
            Metrics are held-out (20% test) results on the demo dataset. The label itself was
            generated from a synthetic rule over the features, so these numbers measure how well
            the forest recovers that rule — <b className="text-slate-400">not real-world landslide
            prediction accuracy</b>. Production deployment needs production-labelled data.
          </p>
        </div>

        {/* Explainability card */}
        <div className="card">
          <h3 className="mb-4 flex items-center gap-2 font-bold">
            <Scale className="h-5 w-5 text-accent" /> Global Feature Importance
          </h3>
          <p className="text-sm text-slate-400">
            Importance the trained forest assigns to each input across the whole model. These are
            model-wide weights, not a per-prediction explanation.
          </p>
          <div className="mt-4 space-y-3">
            {FEATURE_IMPORTANCE.map((f) => (
              <FactorBar key={f.key} factor={f.label} contribution={f.share} max={TOP_SHARE} display="share" />
            ))}
          </div>
          <p className="mt-3 text-[11px] text-slate-500">
            All 12 features sum to 100%. Weather and terrain dominate — consistent with the
            geology-driven landslides of the Northeast.
          </p>
        </div>
      </div>

      {/* Honest scope / known limitations */}
      <div className="card border-amber-900/50">
        <h3 className="mb-3 flex items-center gap-2 font-bold">
          <Info className="h-5 w-5 text-amber-400" aria-hidden="true" /> What these explanations are — and are not
        </h3>
        <ul className="grid gap-2 text-sm text-slate-300 sm:grid-cols-2">
          <li className="rounded-lg bg-surface-light px-3 py-2.5">
            <b className="text-slate-100">Per-run factor bars</b> come from the API's rule-based
            contribution score (0–100 per input), shown on the Prediction page for that run.
          </li>
          <li className="rounded-lg bg-surface-light px-3 py-2.5">
            <b className="text-slate-100">"Model certainty"</b> is how far the probability sits
            from 0.5 (range 55–95). It is not calibrated statistical confidence.
          </li>
          <li className="rounded-lg bg-surface-light px-3 py-2.5">
            <b className="text-slate-100">Risk levels</b> use the published thresholds:
            LOW ≤ 30 · MODERATE ≤ 60 · HIGH ≤ 80 · CRITICAL ≤ 100.
          </li>
          <li className="rounded-lg bg-surface-light px-3 py-2.5">
            <b className="text-slate-100">Not SHAP/LIME</b> and not causal: no per-prediction
            attribution of the forest's internals is claimed anywhere in this UI.
          </li>
        </ul>
        <p className="mt-3 text-[11px] text-slate-500">
          Demo-data caveat: the training label was derived from a thresholded linear score over the
          features (label leakage), so held-out metrics overstate what a deployed model would
          achieve on unseen, naturally-occurring landslides.
        </p>
      </div>

      {/* Future scope */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {[
          { icon: Radar, title: 'Live Sensor Integration', desc: 'Rain gauges, soil probes and IoT stations streaming telemetry to the risk engine in real time.' },
          { icon: GitBranch, title: 'Advanced Deep Learning', desc: 'LSTM/transformer time-series forecasting models can predict risk escalation hours in advance.' },
          { icon: Database, title: 'Satellite & Remote Sensing', desc: 'ISRO/NASA soil-moisture and SAR imagery can extend coverage to un-instrumented areas.' },
          { icon: BellRing, title: 'Public Warning Channels', desc: 'SMS and WhatsApp gateways for pushing alerts to communities and field officers.' },
          { icon: Lightbulb, title: 'Regional Calibration', desc: 'State-specific thresholds and models tuned to local geology and rainfall patterns.' },
          { icon: BrainCircuit, title: 'SHAP Explanations', desc: 'Per-prediction SHAP values could replace the rule-based factor bars for rigorous auditability.' },
        ].map(({ icon: Icon, title, desc }) => (
          <div key={title} className="card">
            <div className="mb-3 inline-flex rounded-lg bg-slate-800 p-2.5">
              <Icon className="h-5 w-5 text-accent" aria-hidden="true" />
            </div>
            <p className="font-bold">{title}</p>
            <p className="mt-2 text-sm text-slate-400">{desc}</p>
          </div>
        ))}
      </div>
      <p className="text-[11px] text-slate-500">
        Future-scope items are ideas, not shipped capabilities.
      </p>
    </div>
  )
}
