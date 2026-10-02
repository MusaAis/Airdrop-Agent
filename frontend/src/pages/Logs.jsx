import React, { useState } from 'react'
import api from '../api'
import useApi from '../hooks/useApi'
import useLiveFeed from '../hooks/useLiveFeed'
import LiveLog from '../components/LiveLog'
import { Card, Badge, PageHeader, EmptyState, DataTable, Segmented } from '../components/ui'
import { fmtDateTime, shortAddr } from '../lib/format'

export default function Logs() {
  const [tab, setTab] = useState('transactions')
  const [filter, setFilter] = useState('')
  const { data, loading, error, reload, refreshing } = useApi(() => api.get('/reports/activity?hours=24').then(r => r.data), [], { interval: 60000 })
  const { connected, events } = useLiveFeed()

  const rows = (Array.isArray(data) ? data : []).filter(l => !filter || JSON.stringify(l).toLowerCase().includes(filter.toLowerCase()))

  const columns = [
    { key: 'created_at', label: 'Time', render: l => <span className="mono muted" style={{ fontSize: 12 }}>{fmtDateTime(l.created_at)}</span> },
    { key: 'wallet', label: 'Wallet', render: l => <span className="mono">{shortAddr(l.wallet)}</span> },
    { key: 'project', label: 'Project' },
    { key: 'task_type', label: 'Task' },
    { key: 'chain', label: 'Chain' },
    { key: 'status', label: 'Status', render: l => <Badge status={l.status}>{l.status}</Badge> },
    { key: 'gas', label: 'Gas $', num: true, render: l => <span className="mono">${l.gas_cost_usd ?? 0}</span> },
  ]

  return (
    <div className="stack">
      <PageHeader
        title="Activity"
        subtitle="Transactions from the last 24 hours, and the live event stream."
        actions={<Segmented value={tab} onChange={setTab} options={[{ value: 'transactions', label: 'Transactions' }, { value: 'live', label: 'Live events' }]} />}
      />

      {tab === 'transactions' ? (
        <Card
          title="Last 24 hours"
          action={<button className="sm" onClick={reload} disabled={refreshing}>{refreshing ? 'Refreshing…' : 'Refresh'}</button>}
        >
          <input placeholder="Filter by wallet, project, task, status…" value={filter} onChange={e => setFilter(e.target.value)} style={{ width: '100%', marginBottom: 14 }} />
          {error && <div className="error" style={{ marginBottom: 12 }}>{error}</div>}
          <DataTable
            columns={columns} rows={rows} loading={loading} skeletonRows={6}
            empty={<EmptyState icon="≡" title={filter ? 'No matching entries' : 'No activity yet'} hint={filter ? 'Try a different filter term.' : 'Activity appears here as tasks execute.'} />}
          />
        </Card>
      ) : (
        <Card
          title="Live events"
          action={
            <span className="row" style={{ gap: 6, fontSize: 12, color: connected ? 'var(--signal)' : 'var(--text-faint)' }}>
              <span className="pulse-dot" style={{ background: connected ? 'var(--signal)' : 'var(--text-faint)', animation: connected ? undefined : 'none' }} />
              {connected ? 'Live' : 'Offline'}
            </span>
          }
        >
          <LiveLog events={events} maxHeight={560} />
        </Card>
      )}
    </div>
  )
}
