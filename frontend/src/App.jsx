import React, { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import api from './api'
import useApi from './hooks/useApi'
import ErrorBoundary from './components/ErrorBoundary'
import { ToastProvider } from './components/Toast'
import { ConfirmProvider } from './components/Confirm'
import Sidebar from './components/Sidebar'
import BottomNav from './components/BottomNav'
import Topbar from './components/Topbar'
import Spinner from './components/Spinner'
import { PAGE_TITLES } from './components/nav'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Wallets from './pages/Wallets'
import Balances from './pages/Balances'
import Chains from './pages/Chains'
import Tasks from './pages/Tasks'
import Projects from './pages/Projects'
import AddProject from './pages/AddProject'
import ProjectDetail from './pages/ProjectDetail'
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

function Shell({ token, logout }) {
  const [collapsed, setCollapsed] = useState(false)
  const location = useLocation()
  const title = PAGE_TITLES[location.pathname] || (/^\/projects\/\d+$/.test(location.pathname) ? 'Project' : 'Airdrop Agent')

  // unresolved-alert badge for the sidebar / bottom bar (the endpoint returns the latest 50)
  const { data: alerts } = useApi(() => api.get('/agent/alerts-list').then(r => r.data), [], { interval: 60000 })
  const alertCount = Array.isArray(alerts) ? alerts.filter(a => !a.resolved).length : 0

  // keep the page scrolled to the top when navigating
  useEffect(() => { window.scrollTo(0, 0) }, [location.pathname])

  return (
    <div className="app">
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(c => !c)} onLogout={logout} alertCount={alertCount} />
      <div className={`app-content${collapsed ? ' collapsed' : ''}`}>
        <Topbar title={title} />
        <main className="main">
          <Routes>
            <Route path="/" element={<Dashboard token={token} />} />
            <Route path="/wallets" element={<Wallets />} />
            <Route path="/balances" element={<Balances />} />
            <Route path="/chains" element={<Chains />} />
            <Route path="/tasks" element={<Tasks />} />
            <Route path="/projects" element={<Projects />} />
            <Route path="/projects/new" element={<AddProject />} />
            <Route path="/projects/:id" element={<ProjectDetail />} />
            <Route path="/logs" element={<Logs />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/faucets" element={<Faucets />} />
            <Route path="/proxies" element={<Proxies />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/claims" element={<Claims />} />
            <Route path="/ai-log" element={<AiLog />} />
            <Route path="/sybil" element={<Sybil />} />
            <Route path="/snapshot" element={<Snapshot />} />
            <Route path="/notifications" element={<Notifications />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </main>
      </div>
      <BottomNav alertCount={alertCount} onLogout={logout} />
    </div>
  )
}

function App() {
  const [token, setToken] = useState(null)
  // 'checking' while we try to resume a session saved by a previous visit
  const [booting, setBooting] = useState(() => !!localStorage.getItem('token'))

  const login = jwt => setToken(jwt)
  const logout = () => { localStorage.removeItem('token'); setToken(null) }

  // Resume the session after a reload / app relaunch. Login already stores the
  // JWT in localStorage (api.js and the WebSocket read it from there), so this
  // adds no new storage — it just stops a reload from discarding it. The token
  // is verified against the API first; an expired one falls back to the login screen.
  useEffect(() => {
    const saved = localStorage.getItem('token')
    if (!saved) { setBooting(false); return }
    api.get('/agent/status')
      .then(() => setToken(saved))
      .catch(() => localStorage.removeItem('token'))
      .finally(() => setBooting(false))
  }, [])

  useEffect(() => {
    const h = () => setToken(null)
    window.addEventListener('auth:expired', h)
    return () => window.removeEventListener('auth:expired', h)
  }, [])

  if (booting) {
    return (
      <div className="login-wrap">
        <Spinner label="Resuming session…" />
      </div>
    )
  }

  return (
    <ErrorBoundary>
      <ToastProvider>
        <ConfirmProvider>
          {!token ? (
            <Login onLogin={login} />
          ) : (
            <BrowserRouter>
              <Shell token={token} logout={logout} />
            </BrowserRouter>
          )}
        </ConfirmProvider>
      </ToastProvider>
    </ErrorBoundary>
  )
}

export default App
