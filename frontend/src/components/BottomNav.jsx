import React, { useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { ALL_ITEMS, NAV_GROUPS, PINNED } from './nav'
import { Icon } from './ui'

/** Phone-only navigation: 4 pinned tabs + a "More" sheet with everything else. */
export default function BottomNav({ alertCount, onLogout }) {
  const [open, setOpen] = useState(false)
  const { pathname } = useLocation()

  // close the sheet whenever the route changes
  useEffect(() => { setOpen(false) }, [pathname])

  const pinned = PINNED.map(to => ALL_ITEMS.find(i => i.to === to))
  const moreActive = !PINNED.includes(pathname) && ALL_ITEMS.some(i => i.to !== '/' && pathname.startsWith(i.to))

  return (
    <>
      <nav className="bottomnav" aria-label="Primary">
        {pinned.map(item => (
          <NavLink key={item.to} to={item.to} end={item.to === '/'} className={({ isActive }) => (isActive ? 'active' : '')}>
            <Icon name={item.icon} size={21} />
            <span>{item.label}</span>
            {item.badge === 'alerts' && alertCount > 0 && <span className="tab-dot" />}
          </NavLink>
        ))}
        <button className={`tab${open || moreActive ? ' active' : ''}`} onClick={() => setOpen(o => !o)} aria-expanded={open} aria-label="More pages">
          <Icon name="more" size={21} />
          <span>More</span>
        </button>
      </nav>

      {open && (
        <>
          <div className="sheet-scrim" onClick={() => setOpen(false)} />
          <div className="sheet" role="dialog" aria-label="All pages">
            <div className="sheet-grip" />
            {NAV_GROUPS.map(g => (
              <div key={g.label} style={{ marginBottom: 14 }}>
                <div className="eyebrow" style={{ margin: '4px 2px 8px' }}>{g.label}</div>
                <div className="sheet-grid">
                  {g.items.map(item => (
                    <NavLink key={item.to} to={item.to} end={item.to === '/'} className={({ isActive }) => `sheet-item${isActive ? ' active' : ''}`}>
                      <Icon name={item.icon} size={22} />
                      {item.label}
                    </NavLink>
                  ))}
                </div>
              </div>
            ))}
            <button className="danger" style={{ width: '100%' }} onClick={onLogout}>Log out</button>
          </div>
        </>
      )}
    </>
  )
}
