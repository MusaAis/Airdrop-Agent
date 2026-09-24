import React, { useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import ErrorBoundary from './components/ErrorBoundary'
import Sidebar from './components/Sidebar'
import Topbar from './components/Topbar'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Wallets from './pages/Wallets'
import Balances from './pages/Balances'
import Chains from './pages/Chains'
import Tasks from './pages/Tasks'
import Projects from './pages/Projects'
import Logs from './pages/Logs'
import Reports from './pages/Reports'
import Settings from './pages/Settings'
import Faucets from './pages/Faucets'
import Proxies from './pages/Proxies'
import Claims from './pages/Claims'
import AiLog from './pages/AiLog'
import Sybil from './pages/Sybil'
import Snapshot from './pages/Snapshot'
import Notifications from './pages/Notifications'
import './index.css'

const PAGE_TITLES = {
  '/': 'Dashboard', '/wallets': 'Wallets', '/balances': 'Balances', '/chains': 'Chains',
  '/tasks': 'Task Configurations', '/projects': 'Projects', '/logs': 'Activity Log',
  '/reports': 'Reports', '/faucets': 'Faucets', '/proxies': 'Proxies',
  '/settings': 'Settings', '/claims': 'Claims', '/ai-log': 'AI Validation Log',
  '/sybil': 'Sybil Risk', '/snapshot': 'Snapshot Calendar', '/notifications': 'Notifications',
}

function Shell({ token, logout }) {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()
  const title = PAGE_TITLES[location.pathname] || 'Airdrop Agent'

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: 'var(--bg)' }}>
      <div className={`sidebar-scrim${mobileOpen ? ' open' : ''}`} onClick={() => setMobileOpen(false)} />
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(c => !c)} onLogout={logout} mobileOpen={mobileOpen} onCloseMobile={() => setMobileOpen(false)} />
      <div className="app-content" style={{ flex: 1, marginLeft: collapsed ? 'var(--sidebar-w-collapsed)' : 'var(--sidebar-w)', transition: 'margin-left 0.2s ease', display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <Topbar title={title} token={token} onOpenMobile={() => setMobileOpen(true)} />
        <main style={{ padding: '24px 28px 48px', flex: 1 }}>
          <Routes>
            <Route path="/" element={<Dashboard token={token} />} />
            <Route path="/wallets" element={<Wallets token={token} />} />
            <Route path="/balances" element={<Balances token={token} />} />
            <Route path="/chains" element={<Chains token={token} />} />
            <Route path="/tasks" element={<Tasks token={token} />} />
            <Route path="/projects" element={<Projects token={token} />} />
            <Route path="/logs" element={<Logs token={token} />} />
            <Route path="/reports" element={<Reports token={token} />} />
            <Route path="/faucets" element={<Faucets token={token} />} />
            <Route path="/proxies" element={<Proxies token={token} />} />
            <Route path="/settings" element={<Settings token={token} />} />
            <Route path="/claims" element={<Claims token={token} />} />
            <Route path="/ai-log" element={<AiLog token={token} />} />
            <Route path="/sybil" element={<Sybil token={token} />} />
            <Route path="/snapshot" element={<Snapshot token={token} />} />
            <Route path="/notifications" element={<Notifications token={token} />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}

function App() {
  // Token in React state only — httpOnly cookie handles persistence
  const [token, setToken] = useState(null)

  const login  = (jwt) => setToken(jwt)
  const logout = () => setToken(null)

  if (!token) return <Login onLogin={login} />

  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Shell token={token} logout={logout} />
      </BrowserRouter>
    </ErrorBoundary>
  )
}

export default App
