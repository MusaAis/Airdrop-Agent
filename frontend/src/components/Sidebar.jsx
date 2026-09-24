import React from 'react'
import { NavLink } from 'react-router-dom'

const ICONS = {
  dashboard:     <path d="M3 13h8V3H3v10zm10 8h8V11h-8v10zM3 21h8v-6H3v6zm10-18v6h8V3h-8z" />,
  wallets:       <path d="M21 7H3a1 1 0 0 0-1 1v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8a1 1 0 0 0-1-1zM3 5h14a2 2 0 0 1 2 2H3z M16.5 14.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z" />,
  balances:      <path d="M12 1v22M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />,
  chains:        <path d="M10.5 13.5l3-3m-5 6 2-2a4 4 0 0 0 0-5.66l-.34-.34a4 4 0 0 0-5.66 0l-2 2a4 4 0 0 0 0 5.66l.34.34M13.5 9.5l-2 2a4 4 0 0 0 0 5.66l.34.34a4 4 0 0 0 5.66 0l2-2a4 4 0 0 0 0-5.66l-.34-.34a4 4 0 0 0-5.66 0z" />,
  tasks:         <path d="M9 11l3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />,
  projects:      <path d="M3 7l9-4 9 4-9 4-9-4zm0 5l9 4 9-4M3 17l9 4 9-4" />,
  logs:          <path d="M4 4h16v4H4zM4 11h10v9H4zM16 11h4v9h-4z" />,
  reports:       <path d="M4 19h16M7 16v-5m5 5V8m5 8v-9" />,
  faucets:       <path d="M12 2.5c3 4 6 7.5 6 11a6 6 0 1 1-12 0c0-3.5 3-7 6-11z" />,
  proxies:       <path d="M8 9h8M8 9a3 3 0 1 1 0-6h1m7 6a3 3 0 1 0 0-6h-1M8 15h8m-8 0a3 3 0 1 0 0 6h1m7-6a3 3 0 1 1 0 6h-1" />,
  claims:        <path d="M12 8v4l3 3m6-3a9 9 0 1 1-18 0 9 9 0 0 1 18 0z" />,
  ailog:         <path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 1 1 7.072 0l-.548.547A3.374 3.374 0 0 0 14 18.469V19a2 2 0 1 1-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />,
  sybil:         <path d="M17 20h5v-2a3 3 0 0 0-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 0 1 5.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 0 1 9.288 0M15 7a3 3 0 1 1-6 0 3 3 0 0 1 6 0z" />,
  snapshot:      <path d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2z" />,
  notifications: <path d="M15 17h5l-1.405-1.405A2.032 2.032 0 0 1 18 14.158V11a6.002 6.002 0 0 0-4-5.659V5a2 2 0 1 0-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 1 1-6 0v-1m6 0H9" />,
  settings:      <path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 13a7.97 7.97 0 0 0 0-2l2-1.6-2-3.4-2.4 1a8 8 0 0 0-1.7-1L15 3h-4l-.3 2.4a8 8 0 0 0-1.7 1l-2.4-1-2 3.4 2 1.6a8 8 0 0 0 0 2l-2 1.6 2 3.4 2.4-1a8 8 0 0 0 1.7 1L11 21h4l.3-2.4a8 8 0 0 0 1.7-1l2.4 1 2-3.4-2-1.6z" />,
}

const NAV = [
  { to: '/',              label: 'Dashboard',     icon: 'dashboard' },
  { to: '/wallets',       label: 'Wallets',        icon: 'wallets' },
  { to: '/balances',      label: 'Balances',       icon: 'balances' },
  { to: '/chains',        label: 'Chains',         icon: 'chains' },
  { to: '/tasks',         label: 'Tasks',          icon: 'tasks' },
  { to: '/projects',      label: 'Projects',       icon: 'projects' },
  { to: '/logs',          label: 'Logs',           icon: 'logs' },
  { to: '/reports',       label: 'Reports',        icon: 'reports' },
  { to: '/faucets',       label: 'Faucets',        icon: 'faucets' },
  { to: '/claims',        label: 'Claims',         icon: 'claims' },
  { to: '/sybil',         label: 'Sybil Risk',     icon: 'sybil' },
  { to: '/snapshot',      label: 'Snapshot Cal.',  icon: 'snapshot' },
  { to: '/ai-log',        label: 'AI Log',         icon: 'ailog' },
  { to: '/notifications', label: 'Notifications',  icon: 'notifications' },
  { to: '/proxies',       label: 'Proxies',        icon: 'proxies' },
  { to: '/settings',      label: 'Settings',       icon: 'settings' },
]

function Icon({ name }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      {ICONS[name]}
    </svg>
  )
}

export default function Sidebar({ collapsed, onToggle, onLogout, mobileOpen, onCloseMobile }) {
  return (
    <aside className={`app-sidebar${mobileOpen ? ' open' : ''}`} style={{ position: 'fixed', top: 0, left: 0, height: '100vh', width: collapsed ? 'var(--sidebar-w-collapsed)' : 'var(--sidebar-w)', background: 'var(--bg-elevated)', borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column', transition: 'width 0.2s ease, transform 0.25s ease', zIndex: 20, overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '20px 18px', height: 32 }}>
        <div style={{ width: 28, height: 28, borderRadius: 8, flexShrink: 0, background: 'linear-gradient(135deg, var(--signal), var(--violet))', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 14, color: '#06151A' }}>A</div>
        {!collapsed && <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 15, whiteSpace: 'nowrap' }}>Airdrop Agent</span>}
      </div>

      <nav style={{ flex: 1, padding: '8px 12px', display: 'flex', flexDirection: 'column', gap: 2, overflowY: 'auto' }}>
        {NAV.map(item => (
          <NavLink key={item.to} to={item.to} end={item.to === '/'} onClick={onCloseMobile} title={collapsed ? item.label : undefined}
            style={({ isActive }) => ({ display: 'flex', alignItems: 'center', gap: 12, padding: collapsed ? '10px 0' : '10px 12px', justifyContent: collapsed ? 'center' : 'flex-start', borderRadius: 'var(--radius-sm)', color: isActive ? 'var(--text)' : 'var(--text-dim)', background: isActive ? 'var(--panel)' : 'transparent', fontWeight: isActive ? 600 : 500, fontSize: 13.5, textDecoration: 'none', position: 'relative', transition: 'background 0.15s ease, color 0.15s ease', whiteSpace: 'nowrap' })}
            className="sidebar-link"
          >
            {({ isActive }) => (
              <>
                {isActive && <span style={{ position: 'absolute', left: -12, top: '50%', transform: 'translateY(-50%)', width: 3, height: 16, borderRadius: 2, background: 'var(--signal)' }} />}
                <span style={{ color: isActive ? 'var(--signal)' : 'inherit', flexShrink: 0, display: 'flex' }}><Icon name={item.icon} /></span>
                {!collapsed && item.label}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div style={{ padding: 12, borderTop: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: 6 }}>
        <button className="ghost sm" onClick={onToggle} style={{ justifyContent: collapsed ? 'center' : 'flex-start', display: 'flex', alignItems: 'center', gap: 10, width: '100%' }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ transform: collapsed ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s', flexShrink: 0 }}>
            <path d="M15 18l-6-6 6-6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          {!collapsed && 'Collapse'}
        </button>
        <button className="ghost sm" onClick={onLogout} style={{ justifyContent: collapsed ? 'center' : 'flex-start', display: 'flex', alignItems: 'center', gap: 10, width: '100%', color: 'var(--rose)' }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
            <path d="M16 17l5-5-5-5" /><path d="M21 12H9" />
          </svg>
          {!collapsed && 'Logout'}
        </button>
      </div>
    </aside>
  )
}
