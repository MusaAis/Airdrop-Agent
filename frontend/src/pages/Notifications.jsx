import React, { useState, useEffect, useCallback } from 'react'
import { API_BASE } from '../api'

const SEV_COLOR = { critical: '#ef4444', warning: '#f59e0b', info: 'var(--signal)' }
const SEV_ICON  = { critical: '🔴', warning: '🟡', info: '🟢' }

export default function Notifications({ token }) {
  const [alerts, setAlerts]  = useState([])
  const [filter, setFilter]  = useState('all')
  const h = { Authorization: `Bearer ${token}` }

  const load = useCallback(async () => {
    try {
      const d = await fetch(`${API_BASE}/agent/alerts-list`, { headers: h }).then(r => r.json())
      setAlerts(Array.isArray(d) ? d : [])
    } catch {}
  }, [token])

  useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t) }, [load])

  const resolve = async (id) => {
    await fetch(`${API_BASE}/agent/alerts/${id}/resolve`, { method: 'POST', headers: h }); load()
  }
  const resolveAll = async () => {
    await fetch(`${API_BASE}/agent/alerts/resolve-all`, { method: 'POST', headers: h }); load()
  }

  const visible = alerts.filter(a => filter === 'all' || a.severity === filter || (filter === 'unresolved' && !a.resolved))
  const unresolved = alerts.filter(a => !a.resolved).length

  const card = { background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: 10, padding: '13px 16px', marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>Notifications</h2>
          {unresolved > 0 && <span style={{ background: '#ef4444', color: '#fff', borderRadius: 99, padding: '2px 9px', fontSize: 12, fontWeight: 700 }}>{unresolved}</span>}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={load} style={{ padding: '7px 14px', borderRadius: 8, background: 'var(--bg-elevated)', border: '1px solid var(--border)', color: 'var(--text)', cursor: 'pointer', fontSize: 13 }}>Refresh</button>
          {unresolved > 0 && <button onClick={resolveAll} style={{ padding: '7px 14px', borderRadius: 8, background: 'var(--signal)', border: 'none', color: '#06151A', fontWeight: 600, cursor: 'pointer', fontSize: 13 }}>Resolve All</button>}
        </div>
      </div>

      {/* Filter tabs */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {['all','unresolved','critical','warning','info'].map(f => (
          <button key={f} onClick={() => setFilter(f)} style={{ padding: '6px 14px', borderRadius: 7, border: '1px solid var(--border)', background: filter === f ? 'var(--signal)' : 'var(--bg-elevated)', color: filter === f ? '#06151A' : 'var(--text)', fontWeight: filter === f ? 600 : 400, cursor: 'pointer', fontSize: 13, textTransform: 'capitalize' }}>{f}</button>
        ))}
      </div>

      {visible.length === 0
        ? <div style={{ ...card, justifyContent: 'center', color: 'var(--text-secondary)', fontSize: 13 }}>No alerts to show.</div>
        : visible.map(a => (
          <div key={a.id} style={{ ...card, opacity: a.resolved ? 0.55 : 1, borderLeft: `3px solid ${SEV_COLOR[a.severity] || 'var(--border)'}` }}>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <span>{SEV_ICON[a.severity] || '⚪'}</span>
                <span style={{ fontWeight: 600, fontSize: 13 }}>{a.type?.replace(/_/g,' ')}</span>
                {a.resolved && <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>resolved</span>}
              </div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 4 }}>{a.message}</div>
              <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{new Date(a.created_at).toLocaleString()}</div>
            </div>
            {!a.resolved && (
              <button onClick={() => resolve(a.id)} style={{ padding: '5px 12px', borderRadius: 6, background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text)', cursor: 'pointer', fontSize: 12, whiteSpace: 'nowrap' }}>Resolve</button>
            )}
          </div>
        ))
      }
    </div>
  )
}
