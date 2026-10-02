import React from 'react'
import { NavLink } from 'react-router-dom'
import { NAV_GROUPS } from './nav'
import { Icon } from './ui'

export default function Sidebar({ collapsed, onToggle, onLogout, alertCount }) {
  return (
    <aside className={`app-sidebar${collapsed ? ' collapsed' : ''}`}>
      <div className="brand">
        <div className="brand-mark">A</div>
        <span className="brand-name">Airdrop Agent</span>
      </div>

      <nav className="nav" aria-label="Main">
        {NAV_GROUPS.map(g => (
          <React.Fragment key={g.label}>
            <div className="nav-group eyebrow">{g.label}</div>
            {g.items.map(item => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                title={collapsed ? item.label : undefined}
                className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
              >
                <span className="nav-icon"><Icon name={item.icon} /></span>
                <span className="nav-label">{item.label}</span>
                {item.badge === 'alerts' && alertCount > 0 && <span className="nav-badge">{alertCount > 99 ? '99+' : alertCount}</span>}
              </NavLink>
            ))}
          </React.Fragment>
        ))}
      </nav>

      <div className="sidebar-foot">
        <button className="ghost sm" onClick={onToggle} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
          <span style={{ display: 'flex', transform: collapsed ? 'rotate(180deg)' : 'none', transition: 'transform .2s' }}><Icon name="collapse" size={16} /></span>
          <span className="nav-label">Collapse</span>
        </button>
        <button className="ghost sm" onClick={onLogout} style={{ color: 'var(--rose)' }}>
          <Icon name="logout" size={16} />
          <span className="nav-label">Log out</span>
        </button>
      </div>
    </aside>
  )
}
