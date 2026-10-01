import React, { useEffect, useRef, useState } from 'react'
import api from '../api'
import WorkerSlotView from '../components/WorkerSlotView'
import ServerStatus from '../components/ServerStatus'
import StatsOverview from '../components/StatsOverview'
import { Card, Badge, EmptyState, StatTile } from '../components/ui'

export default function Dashboard({ token }) {
  const [agentStatus, setAgentStatus] = useState({})
  const [wsLogs, setWsLogs] = useState([])
  const [connected, setConnected] = useState(false)
  const logRef = useRef(null)

  useEffect(() => {
    api.get('/agent/status').then(r => setAgentStatus(r.data)).catch(console.error)
    const backendWs = import.meta.env.VITE_BACKEND_WS_URL || `ws://${window.location.hostname}:8000`
    const ws = new WebSocket(`${backendWs}/ws/logs?token=${localStorage.getItem('token') || ''}`)
    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    ws.onmessage = (e) => {
      setWsLogs(prev => [...prev.slice(-99), JSON.parse(e.data)])
    }
    return () => ws.close()
  }, [])

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [wsLogs])

  const isRunning = agentStatus.status === 'running' || agentStatus.status === 'active'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* top stat row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16 }}>
        <Card>
          <StatTile
            label="Agent status"
            value={agentStatus.status || '—'}
            tone={isRunning ? 'signal' : 'amber'}
            sub={isRunning ? 'Operating normally' : 'Not actively running'}
          />
        </Card>
        <Card>
          <StatTile
            label="Worker slots"
            value={`${agentStatus.worker_slots_active ?? 0}/${agentStatus.worker_slots_max ?? 0}`}
            tone="violet"
            sub="Active / max capacity"
          />
        </Card>
        <Card>
          <StatTile
            label="Live feed"
            value={connected ? 'Online' : 'Offline'}
            tone={connected ? 'signal' : 'rose'}
            sub={connected ? 'Streaming via WebSocket' : 'Reconnecting…'}
          />
        </Card>
      </div>

      <StatsOverview />

      <div className="grid">
        <Card title="Agent overview" action={<Badge status={isRunning ? 'active' : 'paused'}>{agentStatus.status || 'unknown'}</Badge>}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, fontSize: 13.5 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-dim)' }}>Worker capacity</span>
              <span className="mono">{agentStatus.worker_slots_active ?? 0} / {agentStatus.worker_slots_max ?? 0}</span>
            </div>
            <div style={{ height: 6, borderRadius: 4, background: 'var(--bg-elevated)', overflow: 'hidden' }}>
              <div
                style={{
                  height: '100%',
                  borderRadius: 4,
                  background: 'var(--violet)',
                  width: `${agentStatus.worker_slots_max ? (agentStatus.worker_slots_active / agentStatus.worker_slots_max) * 100 : 0}%`,
                  transition: 'width 0.4s ease',
                }}
              />
            </div>
          </div>
        </Card>
        <ServerStatus />
      </div>

      <WorkerSlotView />

      <Card
        title="Live log"
        action={
          <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: connected ? 'var(--signal)' : 'var(--text-faint)' }}>
            <span className="pulse-dot" style={{ background: connected ? 'var(--signal)' : 'var(--text-faint)', animation: connected ? undefined : 'none' }} />
            {connected ? 'Live' : 'Disconnected'}
          </span>
        }
      >
        {wsLogs.length === 0 ? (
          <EmptyState icon="◌" title="Waiting for activity" hint="Log entries will stream here as the agent works." />
        ) : (
          <div
            ref={logRef}
            className="mono"
            style={{
              background: 'var(--bg-elevated)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              padding: 14,
              maxHeight: 280,
              overflowY: 'auto',
              fontSize: 12.5,
              lineHeight: 1.7,
            }}
          >
            {wsLogs.map((l, i) => (
              <div key={i} style={{ color: 'var(--text-dim)', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                <span style={{ color: 'var(--text-faint)' }}>›</span> {JSON.stringify(l)}
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
