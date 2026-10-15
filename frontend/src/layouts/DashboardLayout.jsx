import React, { useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Menu, Home, WifiOff } from 'lucide-react'
import Sidebar from './Sidebar'
import { useAuth } from '../hooks/useAuth'
import { useOnlineStatus } from '../hooks/useOnlineStatus'
import ConnectionStatus from '../components/ConnectionStatus'
import { useEffect } from 'react'

// Browser/tab title per route — an unnamed tab is unusable with many tabs open.
const ROUTE_TITLES = {
  '/dashboard': 'Dashboard',
  '/map': 'Risk Map',
  '/prediction': 'Prediction',
  '/alerts': 'Alerts',
  '/analytics': 'Analytics',
  '/locations': 'Locations',
  '/ai-insights': 'AI Insights',
  '/admin': 'Admin',
  '/settings': 'Settings',
}

export default function DashboardLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const { isAuthed } = useAuth()
  const { isOnline } = useOnlineStatus()
  const navigate = useNavigate()
  const { pathname } = useLocation()

  // Replace instead of pushing so the back button cannot cycle through the
  // protected pages after signing out.
  useEffect(() => {
    if (!isAuthed) navigate('/login', { replace: true })
  }, [isAuthed, navigate])

  useEffect(() => {
    document.title = `${ROUTE_TITLES[pathname] || 'LandslideGuard'} · LandslideGuard AI`
  }, [pathname])

  // Still mounting a protected page briefly would leak its layout, so render
  // nothing until the session check passes.
  if (!isAuthed) return null

  return (
    <div className="min-h-screen bg-slate-950">
      {/* Skip link: first tab stop, visible only when focused. */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:rounded-lg focus:bg-brand focus:px-4 focus:py-2 focus:text-sm focus:font-bold focus:text-slate-900"
      >
        Skip to main content
      </a>
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="lg:pl-64">
        <header className="sticky top-0 z-30 flex items-center justify-between border-b border-slate-800 bg-surface/80 px-4 py-3 backdrop-blur lg:px-8">
          <div className="flex items-center gap-3">
            <button
              className="rounded-lg p-2 text-slate-300 hover:bg-slate-800 lg:hidden"
              onClick={() => setSidebarOpen(true)}
              aria-label="Open navigation menu"
            >
              <Menu className="h-5 w-5" aria-hidden="true" />
            </button>
            <button
              onClick={() => navigate('/')}
              className="flex items-center gap-1.5 text-xs font-medium text-slate-400 transition hover:text-slate-200"
            >
              <Home className="h-4 w-4" aria-hidden="true" /> Landing
            </button>
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-400">
            {/* Per-panel DataSourceBadge reports the real source; this banner
                would otherwise claim DEMO even when LIVE readings are in use. */}
            <span className="hidden items-center gap-1.5 rounded-full bg-slate-800/70 px-3 py-1 font-bold text-slate-400 sm:inline-flex">
              SYNTHETIC TRAINING DATA
            </span>
            <ConnectionStatus />
          </div>
        </header>
        {!isOnline && (
          <div
            role="status"
            className="flex items-start gap-2 border-b border-amber-800/50 bg-amber-950/40 px-4 py-2 text-xs text-amber-200 lg:px-8"
          >
            <WifiOff className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <p>
              You are offline. Live data and actions that need the backend (refresh, predictions,
              alert changes, admin operations) are unavailable. Where possible, last known data is
              shown and clearly labelled as stale. This reconnects automatically.
            </p>
          </div>
        )}
        <main id="main-content" tabIndex={-1} className="p-4 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
