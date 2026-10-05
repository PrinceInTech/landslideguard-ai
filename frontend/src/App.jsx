import React from 'react'
import { Routes, Route } from 'react-router-dom'
import DashboardLayout from './layouts/DashboardLayout'
import Landing from './pages/Landing'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import RiskMapPage from './pages/RiskMapPage'
import Prediction from './pages/Prediction'
import Alerts from './pages/Alerts'
import Analytics from './pages/Analytics'
import Locations from './pages/Locations'
import AIInsights from './pages/AIInsights'
import Admin from './pages/Admin'
import SettingsPage from './pages/SettingsPage'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route element={<DashboardLayout />}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/map" element={<RiskMapPage />} />
        <Route path="/prediction" element={<Prediction />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/locations" element={<Locations />} />
        <Route path="/ai-insights" element={<AIInsights />} />
        <Route path="/admin" element={<Admin />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Landing />} />
    </Routes>
  )
}