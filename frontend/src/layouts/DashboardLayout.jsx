import React, { useState } from 'react'
import { Outlet, useNavigate } from 'react-router-dom'
import { Menu, Home, RefreshCw } from 'lucide-react'
import Sidebar from './Sidebar'
import { useAuth } from '../hooks/useAuth'
import { useEffect } from 'react'

export default function DashboardLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const { isAuthed } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    if (!isAuthed) navigate('/login')
  }, [isAuthed, navigate])

  return (
    <div className="min-h-screen bg-slate-950">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="lg:pl-64">
        <header className="sticky top-0 z-30 flex items-center justify-between border-b border-slate-800 bg-surface/80 px-4 py-3 backdrop-blur lg:px-8">
          <div className="flex items-center gap-3">
            <button
              className="rounded-lg p-2 text-slate-300 hover:bg-slate-800 lg:hidden"
              onClick={() => setSidebarOpen(true)}
            >
              <Menu className="h-5 w-5" />
            </button>
            <button
              onClick={() => navigate('/')}
              className="flex items-center gap-1.5 text-xs font-medium text-slate-400 transition hover:text-slate-200"
            >
              <Home className="h-4 w-4" /> Landing
            </button>
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <span className="hidden items-center gap-1.5 rounded-full bg-amber-500/10 px-3 py-1 font-bold text-amber-400 sm:inline-flex">
              DEMO MODE
            </span>
          </div>
        </header>
        <main className="p-4 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}