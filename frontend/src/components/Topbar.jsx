import React, { useEffect, useState } from 'react'
import api from '../api'

export default function Topbar({ title, onOpenMobile }) {
  const [slots, setSlots] = useState([])
  const [now, setNow] = useState(new Date())

  useEffect(() => {
    const load = () => api.get('/agent/workers').then(r => setSlots(r.data)).catch(() => setSlots([]))
    load()
    const interval = setInterval(load, 5000)
    const clock = setInterval(() => setNow(new Date()), 1000)
    return () => { clearInterval(interval); clearInterval(clock) }
  }, [])

  const activeCount = slots.filter(s => s.status !== 'idle').length

  return (
    <header
      style={{
        height: 60,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 28px',
        borderBottom: '1px solid var(--border)',
        background: 'rgba(11,14,20,0.75)',
        backdropFilter: 'blur(8px)',
        position: 'sticky',
        top: 0,
        zIndex: 10,
        gap: 16,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, minWidth: 0 }}>
        <button
          className="ghost sm hamburger-btn"
          onClick={onOpenMobile}
          aria-label="Open navigation"
          style={{ display: 'none', padding: '7px 9px', flexShrink: 0 }}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M3 6h18M3 12h18M3 18h18" />
          </svg>
        </button>
        <h1 style={{ fontSize: 17, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{title}</h1>
      </div>

      {/* signature element: worker pulse strip */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 18, flex: 1, justifyContent: 'flex-end', minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }} title={`${activeCount} of ${slots.length || 0} worker slots active`}>
          <span className="fleet-label" style={{ fontSize: 11, color: 'var(--text-faint)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600 }}>
            Fleet
          </span>
          <div style={{ display: 'flex', gap: 4 }}>
            {(slots.length ? slots : Array.from({ length: 6 })).slice(0, 12).map((s, i) => {
              const busy = s?.status && s.status !== 'idle'
              return (
                <span
                  key={i}
                  title={busy ? `${s.wallet_id || ''} · ${s.task_type || ''}` : 'idle'}
                  style={{
                    width: 7,
                    height: 18,
                    borderRadius: 2,
                    background: busy ? 'var(--signal)' : 'var(--border)',
                    boxShadow: busy ? '0 0 8px var(--signal-glow)' : 'none',
                    animation: busy ? 'pulse-ring 1.8s ease-in-out infinite' : 'none',
                    transition: 'background 0.3s ease',
                  }}
                />
              )
            })}
          </div>
        </div>

        <div className="mono" style={{ fontSize: 12.5, color: 'var(--text-dim)', minWidth: 64, textAlign: 'right' }}>
          {now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
        </div>
      </div>
    </header>
  )
}
