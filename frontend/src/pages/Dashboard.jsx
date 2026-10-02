import React from 'react'
import api from '../api'
import useApi from '../hooks/useApi'
import useLiveFeed from '../hooks/useLiveFeed'
import WorkerSlotView from '../components/WorkerSlotView'
import ServerStatus from '../components/ServerStatus'
import StatsOverview from '../components/StatsOverview'
import LiveLog from '../components/LiveLog'
import { Card, StatTile, Meter } from '../components/ui'

export default function Dashboard() {
  const { data: status } = useApi(() => api.get('/agent/status').then(r => r.data), [], { interval: 15000 })
  const { connected, events, heartbeat } = useLiveFeed()

  const s = status || {}
  const isRunning = s.status === 'running' || s.status === 'active'
  const slotsActive = heartbeat?.worker_slots_active ?? s.worker_slots_active ?? 0
  const slotsMax = s.worker_slots_max ?? heartbeat?.worker_slots_max ?? 0

  return (
    <div className="stack">
      <div className="grid-stats">
        <Card><StatTile label="Agent" value={s.status || '—'} tone={s.emergency_stop ? 'rose' : isRunning ? 'signal' : 'amber'} sub={s.emergency_stop ? 'EMERGENCY STOP active' : s.dry_run ? 'Dry-run ON' : isRunning ? 'Operating normally' : 'Not actively running'} /></Card>
        <Card>
          <StatTile label="Worker slots" value={`${slotsActive}/${slotsMax}`} tone="violet" sub="Active / max capacity" />
          <div style={{ marginTop: 10 }}><Meter percent={slotsMax ? (slotsActive / slotsMax) * 100 : 0} tone="var(--violet)" /></div>
        </Card>
        <Card><StatTile label="Live feed" value={connected ? 'Online' : 'Offline'} tone={connected ? 'signal' : 'rose'} sub={connected ? 'Streaming via WebSocket' : 'Reconnecting…'} /></Card>
        {heartbeat?.memory_pct != null && (
          <Card><StatTile label="Agent memory" value={`${Math.round(heartbeat.memory_pct)}%`} tone={heartbeat.memory_pct > 85 ? 'rose' : 'default'} sub="from the last heartbeat" /></Card>
        )}
      </div>

      <StatsOverview />

      <div className="grid">
        <ServerStatus />
        <WorkerSlotView />
      </div>

      <Card
        title="Live activity"
        action={
          <span className="row" style={{ gap: 6, fontSize: 12, color: connected ? 'var(--signal)' : 'var(--text-faint)' }}>
            <span className="pulse-dot" style={{ background: connected ? 'var(--signal)' : 'var(--text-faint)', animation: connected ? undefined : 'none' }} />
            {connected ? 'Live' : 'Disconnected'}
          </span>
        }
      >
        <LiveLog events={events} />
      </Card>
    </div>
  )
}
