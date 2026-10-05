import React from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard,
  Map as MapIcon,
  BrainCircuit,
  Bell,
  BarChart3,
  MapPin,
  Sparkles,
  ShieldCheck,
  Settings,
  Mountain,
  LogOut,
  User,
} from 'lucide-react'
import { useAuth } from '../hooks/useAuth'

const NAV = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/map', label: 'Risk Map', icon: MapIcon },
  { to: '/prediction', label: 'Prediction', icon: BrainCircuit },
  { to: '/alerts', label: 'Alerts', icon: Bell },
  { to: '/analytics', label: 'Analytics', icon: BarChart3 },
  { to: '/locations', label: 'Locations', icon: MapPin },
  { to: '/ai-insights', label: 'AI Insights', icon: Sparkles },
  { to: '/admin', label: 'Admin', icon: ShieldCheck },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export default function Sidebar({ open, onClose }) {
  const { logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/')
  }

  return (
    <>
      {open && (
        <div className="fixed inset-0 z-40 bg-slate-950/70 lg:hidden" onClick={onClose} />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-slate-800 bg-surface transition-transform lg:translate-x-0 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex items-center gap-3 border-b border-slate-800 px-5 py-5">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand/20">
            <Mountain className="h-6 w-6 text-brand" />
          </div>
          <div>
            <p className="text-sm font-extrabold leading-tight text-slate-100">LandslideGuard AI</p>
            <p className="text-[10px] font-medium uppercase tracking-wider text-slate-500">NER Risk Monitor</p>
          </div>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              onClick={onClose}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition ${
                  isActive
                    ? 'bg-brand/15 text-brand'
                    : 'text-slate-400 hover:bg-slate-800 hover:text-slate-100'
                }`
              }
            >
              <Icon className="h-4.5 w-4.5 h-5 w-5" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-slate-800 p-3">
          <div className="mb-2 flex items-center gap-3 rounded-lg bg-slate-800/60 px-3 py-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-brand/20">
              <User className="h-4 w-4 text-brand" />
            </div>
            <div className="min-w-0">
              <p className="truncate text-xs font-semibold text-slate-200">Admin</p>
              <p className="text-[10px] text-slate-500">Monitoring Authority</p>
            </div>
            <button onClick={handleLogout} className="ml-auto text-slate-400 transition hover:text-red-400" title="Logout">
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </aside>
    </>
  )
}