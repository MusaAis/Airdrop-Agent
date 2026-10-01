import React, { useEffect, useState, useCallback } from 'react'
import api from '../api'
import { Card, Badge } from './ui'

export default function SystemPanel() {
  const [s, setS] = useState(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  const load = useCallback(() => api.get('/ops/system').then(r => setS(r.data)).catch(() => setMsg('Could not load system state.')), [])
  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t) }, [load])

  const run = async (fn) => {
    setBusy(true); setMsg('')
    try { await fn() } catch (e) { setMsg(e?.response?.data?.detail || 'Request failed.') } finally { setBusy(false) }
  }

  const toggleDry = () => run(async () => {
    const r = await api.post('/ops/system/dry-run', { enabled: !s.dry_run })
    setS(r.data)
  })
  const clearStop = () => run(async () => {
    if (!window.confirm('Clear the emergency stop? Start the agent afterwards if it is stopped.')) return
    const r = await api.post('/ops/system/emergency/clear')
    setS(r.data); setMsg(r.data.message)
  })
  const archive = () => run(async () => {
    const r = await api.post('/ops/system/archive-logs')
    setMsg(`Archived ${r.data.logs_archived} log(s), purged ${r.data.rpc_logs_purged} RPC log(s).`)
  })

  return (
    <Card title="System controls">
      {!s ? <div className="skeleton" style={{ height: 50, borderRadius: 10 }} /> : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
            <Badge status={s.agent_running ? 'active' : 'paused'}>agent {s.agent_running ? 'running' : 'stopped'}</Badge>
            <Badge status={s.dry_run ? 'pending' : 'active'}>{s.dry_run ? 'dry-run ON' : 'live'}</Badge>
            {s.emergency_stop && <Badge status="failed">emergency stop</Badge>}
          </div>

          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
            <button className={s.dry_run ? 'primary sm' : 'sm'} onClick={toggleDry} disabled={busy}>
              {s.dry_run ? 'Turn dry-run OFF (go live)' : 'Turn dry-run ON'}
            </button>
            {s.emergency_stop && <button className="sm danger" onClick={clearStop} disabled={busy}>Clear emergency stop</button>}
            <button className="ghost sm" onClick={archive} disabled={busy}>Archive old logs now</button>
          </div>
          <p style={{ fontSize: 12, color: 'var(--text-faint)', margin: 0 }}>
            Dry-run simulates every task and broadcasts nothing. It is kept in memory, so it resets to OFF when the backend restarts.
          </p>
          {msg && <div style={{ fontSize: 13, color: 'var(--text-dim)' }}>{msg}</div>}
        </div>
      )}
    </Card>
  )
}
