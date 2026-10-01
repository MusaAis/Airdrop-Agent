import React, { useState, useEffect, useCallback } from 'react'
import { API_BASE } from '../api'

export default function Snapshot({ token }) {
  const [projects, setProjects] = useState([])
  const h = { Authorization: `Bearer ${token}` }

  const load = useCallback(async () => {
    try {
      const d = await fetch(`${API_BASE}/projects/`, { headers: h }).then(r => r.json())
      const today = new Date()
      const withDays = (Array.isArray(d) ? d : [])
        .filter(p => p.airdrop_date || p.tge_date)
        .map(p => {
          const date = p.airdrop_date || p.tge_date
          const days = Math.ceil((new Date(date) - today) / 86400000)
          return { ...p, deadline: date, days }
        })
        .sort((a, b) => a.days - b.days)
      setProjects(withDays)
    } catch {}
  }, [token])

  useEffect(() => { load() }, [load])

  const flag = d => d <= 0 ? '💥' : d <= 7 ? '🔴' : d <= 30 ? '🟡' : '🟢'
  const bar  = d => Math.max(0, Math.min(100, 100 - (d / 90) * 100))
  const card = { background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: 10, padding: '16px 20px', marginBottom: 10 }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>Snapshot Calendar</h2>
        <button onClick={load} style={{ padding: '7px 16px', borderRadius: 8, background: 'var(--bg-elevated)', border: '1px solid var(--border)', color: 'var(--text)', cursor: 'pointer' }}>Refresh</button>
      </div>

      {projects.length === 0
        ? <div style={{ ...card, color: 'var(--text-secondary)', fontSize: 13 }}>No snapshot deadlines configured. Set airdrop_date or tge_date on your projects.</div>
        : projects.map(p => (
          <div key={p.id} style={card}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <div>
                <span style={{ fontWeight: 600, fontSize: 14 }}>{flag(p.days)} {p.name}</span>
                <span style={{ marginLeft: 10, fontSize: 12, color: 'var(--text-secondary)' }}>{p.deadline}</span>
              </div>
              <span style={{ fontWeight: 700, fontSize: 14, color: p.days <= 7 ? '#ef4444' : p.days <= 30 ? '#f59e0b' : 'var(--signal)' }}>
                {p.days <= 0 ? 'PASSED' : `${p.days}d left`}
              </span>
            </div>
            <div style={{ height: 6, background: 'var(--bg)', borderRadius: 99, overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${bar(p.days)}%`, background: p.days <= 7 ? '#ef4444' : p.days <= 30 ? '#f59e0b' : 'var(--signal)', borderRadius: 99, transition: 'width .4s' }} />
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 6 }}>Priority: {p.priority} · Status: {p.status}</div>
          </div>
        ))
      }
    </div>
  )
}
