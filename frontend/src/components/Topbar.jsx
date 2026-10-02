import React, { useEffect, useState } from 'react'
import api from '../api'
import useApi from '../hooks/useApi'

export default function Topbar({ title }) {
  const { data } = useApi(() => api.get('/agent/workers').then(r => r.data), [], { interval: 5000 })
  const slots = Array.isArray(data) ? data : []
  const [now, setNow] = useState(new Date())

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(t)
  }, [])

  const activeCount = slots.filter(s => s.status !== 'idle').length

  return (
    <header className="topbar">
      <h1>{title}</h1>
      <div className="topbar-right">
        <div className="fleet" title={`${activeCount} of ${slots.length} worker slots active`}>
          <span className="eyebrow fleet-label">Fleet</span>
          <div className="fleet-bars">
            {(slots.length ? slots : Array.from({ length: 6 })).slice(0, 12).map((s, i) => {
              const busy = s?.status && s.status !== 'idle'
              return <span key={i} className={`fleet-bar${busy ? ' busy' : ''}`} title={busy ? `${s.wallet_id || ''} · ${s.task_type || ''}` : 'idle'} />
            })}
          </div>
        </div>
        <div className="mono clock">{now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</div>
      </div>
    </header>
  )
}
