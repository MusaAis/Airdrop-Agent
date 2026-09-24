import React, { useEffect, useState } from 'react'
import api from '../api'
import { Card, Badge, EmptyState, SkeletonRows } from '../components/ui'

export default function Logs() {
  const [logs, setLogs] = useState([])
  const [filter, setFilter] = useState('')
  const [loaded, setLoaded] = useState(false)
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    api.get('/reports/activity?hours=24').then(r => { setLogs(Array.isArray(r.data) ? r.data : []); setLoaded(true) }).catch(() => setLoaded(true))
    const backendWs = import.meta.env.VITE_BACKEND_WS_URL || `ws://${window.location.hostname}:8000`
    const ws = new WebSocket(`${backendWs}/ws/logs?token=${localStorage.getItem('token') || ''}`)
    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    ws.onmessage = (e) => {
      setLogs(prev => [JSON.parse(e.data), ...prev.slice(0, 199)])
    }
    return () => ws.close()
  }, [])

  const filtered = (Array.isArray(logs) ? logs : []).filter(l => JSON.stringify(l).toLowerCase().includes(filter.toLowerCase()))

  return (
    <Card
      title="Activity log · last 24h"
      action={
        <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: connected ? 'var(--signal)' : 'var(--text-faint)' }}>
          <span className="pulse-dot" style={{ background: connected ? 'var(--signal)' : 'var(--text-faint)', animation: connected ? undefined : 'none' }} />
          {connected ? 'Live' : 'Offline'}
        </span>
      }
    >
      <input
        placeholder="Filter by wallet, project, task, status…"
        value={filter}
        onChange={e => setFilter(e.target.value)}
        style={{ width: '100%', marginBottom: 14 }}
      />
      <div className="table-scroll"><table>
        <thead>
          <tr><th>Time</th><th>Wallet</th><th>Project</th><th>Task</th><th>Status</th><th style={{ textAlign: 'right' }}>Gas $</th></tr>
        </thead>
        <tbody>
          {!loaded && <SkeletonRows rows={6} cols={6} />}
          {loaded && filtered.map((l, i) => (
            <tr key={i}>
              <td className="mono" style={{ color: 'var(--text-dim)', fontSize: 12 }}>{l.created_at}</td>
              <td className="mono">{l.wallet}</td>
              <td>{l.project}</td>
              <td>{l.task_type}</td>
              <td><Badge status={l.status}>{l.status}</Badge></td>
              <td className="mono" style={{ textAlign: 'right' }}>${l.gas_cost_usd}</td>
            </tr>
          ))}
        </tbody>
      </table></div>
      {loaded && filtered.length === 0 && (
        <EmptyState icon="≡" title={filter ? 'No matching entries' : 'No activity yet'} hint={filter ? 'Try a different filter term.' : 'Activity will appear here as tasks execute.'} />
      )}
    </Card>
  )
}
