import React, { useState } from 'react'
import api from '../api'
import useApi, { apiError } from '../hooks/useApi'
import { useToast } from './Toast'
import { useConfirm } from './Confirm'
import { Card, Badge, SkeletonBlock } from './ui'

export default function SystemPanel() {
  const toast = useToast()
  const confirm = useConfirm()
  const { data: s, reload } = useApi(() => api.get('/ops/system').then(r => r.data), [], { interval: 15000 })
  const [busy, setBusy] = useState(false)
  const [pw, setPw] = useState('')

  // run an API call, toast its message, then refresh (agent start/stop take a moment to show)
  const act = async (fn, ask) => {
    if (ask && !(await confirm(ask))) return
    setBusy(true)
    try {
      const r = await fn()
      if (r?.data?.message) toast.success(r.data.message)
    } catch (e) { toast.error(apiError(e)) }
    finally { setBusy(false); reload(); setTimeout(reload, 1500) }
  }

  const unlock = () => pw && act(async () => {
    const r = await api.post('/ops/system/unlock', { master_password: pw })
    setPw('')
    return r
  })

  return (
    <Card title="System controls">
      {!s ? <SkeletonBlock height={50} /> : (
        <div className="stack-sm" style={{ gap: 14 }}>
          <div className="row">
            <Badge status={s.agent_running ? 'active' : 'paused'}>agent {s.agent_running ? 'running' : 'stopped'}</Badge>
            <Badge status={s.dry_run ? 'pending' : 'active'}>{s.dry_run ? 'dry-run ON' : 'live'}</Badge>
            <Badge status={s.seed_loaded ? 'active' : 'failed'}>{s.seed_loaded ? 'seed unlocked' : 'seed locked'}</Badge>
            {s.emergency_stop && <Badge status="failed">emergency stop</Badge>}
          </div>

          {!s.seed_loaded && (
            <div className="stack-sm">
              <div className="row" style={{ flexWrap: 'nowrap' }}>
                <input
                  className="grow" type="password" placeholder="Master password" value={pw}
                  onChange={e => setPw(e.target.value)} onKeyDown={e => e.key === 'Enter' && unlock()}
                  autoComplete="current-password"
                />
                <button className="primary sm" onClick={unlock} disabled={busy || !pw}>Unlock seed</button>
              </div>
              <p className="hint">The seed lives in memory only, so it is locked after every backend restart. While locked, HD wallets are not scheduled.</p>
            </div>
          )}

          <div className="row">
            {!s.agent_running && !s.emergency_stop && (
              <button className="primary sm" disabled={busy} onClick={() => act(() => api.post('/ops/system/agent/start'))}>Start agent</button>
            )}
            {s.agent_running && (
              <button className="sm" disabled={busy}
                onClick={() => act(() => api.post('/ops/system/agent/stop'), { title: 'Stop the agent?', message: 'Tasks already running will finish first.', confirmLabel: 'Stop agent', tone: 'danger' })}>
                Stop agent
              </button>
            )}
            {!s.emergency_stop && (
              <button className="sm danger" disabled={busy}
                onClick={() => act(() => api.post('/agent/kill', null, { params: { reason: 'dashboard' } }), { title: 'Emergency stop?', message: 'Clears the queue and halts the agent. A transaction that is already broadcast cannot be undone.', confirmLabel: 'Emergency stop', tone: 'danger' })}>
                Emergency stop
              </button>
            )}
            {s.emergency_stop && (
              <button className="sm danger" disabled={busy}
                onClick={() => act(() => api.post('/ops/system/emergency/clear'), { title: 'Clear the emergency stop?', message: 'Start the agent afterwards.', confirmLabel: 'Clear stop' })}>
                Clear emergency stop
              </button>
            )}
            <button className={s.dry_run ? 'primary sm' : 'sm'} disabled={busy} onClick={() => act(() => api.post('/ops/system/dry-run', { enabled: !s.dry_run }))}>
              {s.dry_run ? 'Turn dry-run OFF (go live)' : 'Turn dry-run ON'}
            </button>
            <button className="ghost sm" disabled={busy} onClick={() => act(async () => {
              const r = await api.post('/ops/system/archive-logs')
              return { data: { message: `Archived ${r.data.logs_archived} log(s), purged ${r.data.rpc_logs_purged} RPC log(s).` } }
            })}>Archive old logs now</button>
          </div>
          <p className="hint faint">
            Dry-run: tasks you trigger manually are simulated and nothing is broadcast, and automatic queue filling is paused while it is on.
            The setting is saved and survives restarts (DRY_RUN_MODE=true in .env also forces it on at every boot). The emergency stop is saved the same way and stays active after a restart until you clear it.
          </p>
        </div>
      )}
    </Card>
  )
}
