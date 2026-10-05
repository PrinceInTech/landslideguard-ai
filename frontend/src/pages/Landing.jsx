import React from 'react'
import { Link } from 'react-router-dom'
import {
  Mountain,
  BrainCircuit,
  Radar,
  BellRing,
  Map as MapIcon,
  BarChart3,
  ShieldCheck,
  Wind,
  Satellite,
  Database,
  Cpu,
  Layers,
  Activity,
  Twitter,
  Github,
} from 'lucide-react'

const HOW_IT_WORKS = [
  {
    icon: Radar,
    title: '1. Ingest Environmental Data',
    desc: 'Weather, rainfall, soil moisture, slope and elevation inputs are collected from APIs, sensors and GIS layers per monitoring location.',
  },
  {
    icon: Cpu,
    title: '2. AI/ML Risk Engine',
    desc: 'A trained Random Forest model analyzes the features and predicts a landslide risk score from 0–100 with confidence and explainable factors.',
  },
  {
    icon: BellRing,
    title: '3. Early Warning & Alerts',
    desc: 'Risk escalations automatically generate warnings and emergency alerts with recommended actions for district authorities.',
  },
  {
    icon: MapIcon,
    title: '4. GIS Visualization',
    desc: 'Every location is rendered on an interactive map of Northeast India with live risk markers and environmental conditions.',
  },
]

const FEATURES = [
  {
    icon: BrainCircuit,
    title: 'Predictive Risk Scoring',
    desc: 'Machine-learning-driven landslide risk scores (0–100) for all monitored locations.',
  },
  {
    icon: ShieldCheck,
    title: 'Explainable AI',
    desc: 'See exactly which factors — rainfall, slope, soil moisture — drive every risk rating.',
  },
  {
    icon: BellRing,
    title: 'Early Warning Engine',
    desc: 'Moderate, High and Critical alerts with recommended actions, ready for authorities.',
  },
  {
    icon: BarChart3,
    title: 'Historical Analytics',
    desc: 'Monthly trends, rainfall correlation and state-wise incident analytics from real data pipelines.',
  },
  {
    icon: Satellite,
    title: 'Scalable Data Feeds',
    desc: 'Architected to plug in ISRO satellite data, IoT sensors and government disaster databases later.',
  },
  {
    icon: Layers,
    title: '8 States, One Platform',
    desc: 'Full coverage of every North Eastern state: Arunachal Pradesh to Tripura.',
  },
]

const STACK = [
  { icon: BrainCircuit, label: 'Scikit-learn' },
  { icon: Cpu, label: 'FastAPI' },
  { icon: Layers, label: 'React + Vite' },
  { icon: MapIcon, label: 'Leaflet GIS' },
  { icon: BarChart3, label: 'Recharts' },
  { icon: Database, label: 'SQLite / MongoDB' },
  { icon: Wind, label: 'OpenWeatherMap' },
  { icon: Activity, label: 'Pandas / NumPy' },
]

export default function Landing() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      {/* Nav */}
      <nav className="sticky top-0 z-40 border-b border-slate-800/70 bg-slate-950/85 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-3.5">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand/20">
              <Mountain className="h-5 w-5 text-brand" />
            </div>
            <div>
              <p className="text-sm font-extrabold leading-tight">LandslideGuard AI</p>
              <p className="text-[10px] uppercase tracking-wider text-slate-500">MDoNER · SIH 2026</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Link to="/login" className="text-sm font-medium text-slate-300 transition hover:text-white">
              Login
            </Link>
            <Link to="/dashboard" className="btn-primary !py-2">
              Open Risk Dashboard
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(245,158,11,0.12),transparent_55%)]" />
        <div className="mx-auto max-w-7xl px-5 pb-20 pt-20 text-center lg:pt-28">
          <div className="mx-auto mb-5 inline-flex items-center gap-2 rounded-full border border-amber-500/30 bg-amber-500/10 px-4 py-1.5 text-xs font-bold text-amber-400">
            <Radar className="h-3.5 w-3.5" /> Smart India Hackathon 2026 · Problem SIH26001
          </div>
          <h1 className="mx-auto max-w-4xl text-4xl font-black leading-tight tracking-tight sm:text-5xl lg:text-6xl">
            AI-Powered Landslide{' '}
            <span className="bg-gradient-to-r from-amber-400 to-orange-500 bg-clip-text text-transparent">
              Early Warning System
            </span>
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-lg text-slate-400">
            Predict. Monitor. Warn. Protect. Real-time landslide risk monitoring for the North
            Eastern Region of India using machine learning and GIS.
          </p>
          <div className="mt-9 flex flex-col items-center justify-center gap-4 sm:flex-row">
            <Link to="/dashboard" className="btn-primary !px-6 !py-3 text-base">
              Open Risk Dashboard
            </Link>
            <Link to="/map" className="btn-outline !px-6 !py-3 text-base">
              <MapIcon className="h-4 w-4" /> Explore Risk Map
            </Link>
          </div>
          <div className="mt-14 grid grid-cols-2 gap-4 text-left sm:grid-cols-4">
            {[
              ['8', 'NER States Covered'],
              ['30', 'Monitoring Locations'],
              ['0–100', 'AI Risk Score Range'],
              ['24×7', 'Continuous Monitoring'],
            ].map(([v, l]) => (
              <div key={l} className="rounded-xl border border-slate-800 bg-surface p-4">
                <p className="text-2xl font-extrabold text-brand">{v}</p>
                <p className="mt-1 text-xs text-slate-400">{l}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Problem / Solution */}
      <section className="border-y border-slate-800 bg-surface/40 py-16">
        <div className="mx-auto grid max-w-7xl gap-10 px-5 lg:grid-cols-2">
          <div>
            <p className="text-xs font-bold uppercase tracking-widest text-red-400">The Problem</p>
            <h2 className="mt-3 text-2xl font-extrabold lg:text-3xl">
              2,300+ landslides a year. Mostly preventable losses.
            </h2>
            <p className="mt-4 text-slate-400">
              Northeast India sits in one of the most landslide-prone zones on Earth. Monsoon rains,
              steep slopes and fragile geology combine to cause frequent, deadly landslides. Responding
              after the event is too late — communities need <b className="text-slate-200">prediction and early warning</b>.
            </p>
            <ul className="mt-5 space-y-2 text-sm text-slate-300">
              <li>• Heavy rainfall &amp; soil saturation saturate slopes every monsoon</li>
              <li>• Limited real-time risk visibility for district authorities</li>
              <li>• No unified platform connecting weather → risk → warning</li>
            </ul>
          </div>
          <div>
            <p className="text-xs font-bold uppercase tracking-widest text-emerald-400">Our Solution</p>
            <h2 className="mt-3 text-2xl font-extrabold lg:text-3xl">
              LandslideGuard AI turns data into action.
            </h2>
            <p className="mt-4 text-slate-400">
              An end-to-end AI platform that ingests environmental data, predicts landslide risk with
              explainable machine learning, plots risk live on a GIS map of the NER, and issues
              graded early warnings automatically.
            </p>
            <ul className="mt-5 space-y-2 text-sm text-slate-300">
              <li>• Real ML model — not a mock-up — with honest accuracy reporting</li>
              <li>• Explainable risk scores: rainfall, slope, moisture and more</li>
              <li>• Model-agnostic API ready for ISRO, IoT and weather feeds</li>
            </ul>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="mx-auto max-w-7xl px-5 py-16">
        <p className="text-center text-xs font-bold uppercase tracking-widest text-brand">How It Works</p>
        <h2 className="mt-2 text-center text-2xl font-extrabold lg:text-3xl">From raw data to early warning</h2>
        <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {HOW_IT_WORKS.map(({ icon: Icon, title, desc }) => (
            <div key={title} className="card transition hover:border-brand/40">
              <div className="mb-4 inline-flex rounded-lg bg-brand/15 p-3">
                <Icon className="h-6 w-6 text-brand" />
              </div>
              <p className="font-bold">{title}</p>
              <p className="mt-2 text-sm text-slate-400">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Features */}
      <section className="border-y border-slate-800 bg-surface/40 py-16">
        <div className="mx-auto max-w-7xl px-5">
          <p className="text-center text-xs font-bold uppercase tracking-widest text-brand">Capabilities</p>
          <h2 className="mt-2 text-center text-2xl font-extrabold lg:text-3xl">A complete disaster-management platform</h2>
          <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map(({ icon: Icon, title, desc }) => (
              <div key={title} className="card">
                <div className="mb-4 inline-flex rounded-lg bg-slate-800 p-2.5">
                  <Icon className="h-5 w-5 text-accent" />
                </div>
                <p className="font-bold">{title}</p>
                <p className="mt-2 text-sm text-slate-400">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Tech stack */}
      <section className="mx-auto max-w-7xl px-5 py-16">
        <p className="text-center text-xs font-bold uppercase tracking-widest text-brand">Technology Stack</p>
        <h2 className="mt-2 text-center text-2xl font-extrabold">Built on battle-tested open source</h2>
        <div className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
          {STACK.map(({ icon: Icon, label }) => (
            <div key={label} className="flex items-center gap-3 rounded-xl border border-slate-800 bg-surface px-4 py-3">
              <Icon className="h-5 w-5 text-slate-400" />
              <span className="text-sm font-medium text-slate-300">{label}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Impact + CTA */}
      <section className="border-t border-slate-800 bg-gradient-to-b from-slate-900 to-slate-950 py-16">
        <div className="mx-auto max-w-4xl px-5 text-center">
          <p className="text-xs font-bold uppercase tracking-widest text-brand">Impact</p>
          <h2 className="mt-3 text-2xl font-extrabold lg:text-4xl">
            Earlier warnings. Faster response.
            <br />
            <span className="text-slate-400">Fewer lives lost.</span>
          </h2>
          <p className="mx-auto mt-4 max-w-2xl text-slate-400">
            By identifying vulnerable locations before severe events and standardizing warnings for
            authorities, LandslideGuard AI supports proactive evacuation and emergency planning across
            the North Eastern Region.
          </p>
          <div className="mt-9 flex flex-col items-center justify-center gap-4 sm:flex-row">
            <Link to="/dashboard" className="btn-primary !px-6 !py-3 text-base">
              Open Risk Dashboard
            </Link>
            <Link to="/map" className="btn-outline !px-6 !py-3 text-base">
              Explore Risk Map
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-slate-800 py-8">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-4 px-5 sm:flex-row">
          <div className="flex items-center gap-2">
            <Mountain className="h-5 w-5 text-brand" />
            <p className="text-sm font-bold">LandslideGuard AI</p>
            <span className="text-xs text-slate-500">· SIH 2026 · MDoNER</span>
          </div>
          <p className="text-xs text-slate-500">
            AI-Powered Early Warning &amp; Landslide Risk Monitoring System for Northeast India
          </p>
        </div>
      </footer>
    </div>
  )
}