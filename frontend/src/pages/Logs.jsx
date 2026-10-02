import React, { useMemo, useState } from 'react'
import api from '../api'
import useApi from '../hooks/useApi'
import useLiveFeed from '../hooks/useLiveFeed'
import { Card, Badge, PageHeader, EmptyState, DataTable, Segmented } from '../components/ui'
import { fmtDateTime, shortAddr } from '../lib/format'

const tone = s => (s === 'success' || s === 'confirmed' ? 'success' : s === 'failed' || s === 'stuck' ? 'danger' : 'warning')

function ActivityTab() {
  const { connected, events } = useLiveFeed({ history: 200, max: 300 })
  const { data: projects } = useApi(
    () => api.get('/projects/', { params: { include_archived: true } }).then(r => Object.fromEntries(r.data.map(p => [p.id, p.name]))),
    [],
  )
  const [filter, setFilter] = useState('')
  const [status, setStatus] = useState('')

  const rows = useMemo(() => events.filter(l =>
    (!status || l.status === status) && JSON.stringify(l).toLowerCase().includes(filter.toLowerCase())), [events, filter, status])

  const cols = [
    { key: 'time', label: 'Time', render: l => <span className="mono muted" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>{fmtDateTime(l.created_at)}</span> },
    { key: 'wallet', label: 'Wallet', render: l => <span className="mono">#{l.wallet_id ?? '?'}</span> },
    { key: 'project', label: 'Project', render: l => (projects || {})[l.project_id] || (l.project_id ? `#${l.project_id}` : '—') },
    { key: 'task', label: 'Task', render: l => l.task_name || '—' },
    { key: 'status', label: 'Status', render: l => <Badge tone={tone(l.status)}>{l.status}</Badge> },
    {
      key: 'detail', label: 'Detail',
      render: l => (
        <span className="mono" style={{ fontSize: 12, color: l.error_message ? 'var(--rose)' : 'var(--text-faint)', overflowWrap: 'anywhere', textAlign: 'right' }}>
          {l.error_message || (l.tx_hash ? `0x${l.tx_hash.replace(/^0x/, '').slice(0, 14)}…` : '')}
        </span>
      ),
    },
  ]

  return (
    <Card
      title="Task activity"
      action={
        <span className="row" style={{ gap: 6, fontSize: 12, color: connected ? 'var(--signal)' : 'var(--text-faint)' }}>
          <span className="pulse-dot" style={{ background: connected ? 'var(--signal)' : 'var(--text-faint)', animation: connected ? undefined : 'none' }} />
          {connected ? 'Live' : 'Offline'}
        </span>
      }
    >
      <div className="row" style={{ marginBottom: 14, flexWrap: 'nowrap' }}>
        <input className="grow" placeholder="Filter by wallet id, task, error…" value={filter} onChange={e => setFilter(e.target.value)} />
        <select value={status} onChange={e => setStatus(e.target.value)}>
          <option value="">all</option><option value="success">success</option><option value="failed">failed</option><option value="simulated">simulated</option>
        </select>
      </div>
      <DataTable
        columns={cols} rows={rows} rowKey="id"
        empty={<EmptyState icon="≡" title={filter || status ? 'No matching entries' : 'No activity yet'} hint={filter || status ? 'Try a different filter.' : 'Results appear here as tasks run.'} />}
      />
    </Card>
  )
}

function TransactionsTab() {
  const [status, setStatus] = useState('')
  const [hours, setHours] = useState(168)
  const { data, loading, error, reload, refreshing } = useApi(
    () => api.get('/ops/transactions', { params: { hours, status: status || undefined, limit: 200 } }).then(r => r.data),
    [status, hours],
  )
  const rows = Array.isArray(data) ? data : []

  const cols = [
    { key: 'time', label: 'Time', render: t => <span className="mono muted" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>{fmtDateTime(t.created_at)}</span> },
    { key: 'wallet', label: 'Wallet', render: t => <span className="mono">#{t.wallet_id} {shortAddr(t.wallet)}</span> },
    { key: 'chain', label: 'Chain' },
    { key: 'pt', label: 'Project · task', render: t => <span style={{ fontSize: 12.5 }}>{t.project || '—'} · {t.task_type || '—'}</span> },
    { key: 'status', label: 'Status', render: t => <Badge tone={tone(t.status)}>{t.status}</Badge> },
    {
      key: 'tx', label: 'Tx',
      render: t => <span className="mono" style={{ fontSize: 12 }}>{t.explorer_url ? <a href={t.explorer_url} target="_blank" rel="noreferrer">{shortAddr(t.tx_hash)}</a> : shortAddr(t.tx_hash) || '—'}</span>,
    },
    { key: 'error', label: 'Error', render: t => <span className="mono" style={{ fontSize: 12, color: 'var(--rose)', overflowWrap: 'anywhere', textAlign: 'right' }}>{t.error || ''}</span> },
  ]

  return (
    <Card title="On-chain transactions" action={<button className="sm" onClick={reload} disabled={refreshing}>{refreshing ? 'Refreshing…' : 'Refresh'}</button>}>
      <div className="row" style={{ marginBottom: 14 }}>
        <select value={status} onChange={e => setStatus(e.target.value)}>
          <option value="">all statuses</option>
          {['confirmed', 'pending', 'failed', 'replaced', 'cancelled', 'stuck'].map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={hours} onChange={e => setHours(Number(e.target.value))}>
          <option value={24}>last 24h</option><option value={168}>last 7 days</option><option value={720}>last 30 days</option>
        </select>
      </div>
      {error && <div className="error" style={{ marginBottom: 10 }}>{error}</div>}
      <DataTable
        columns={cols} rows={rows} loading={loading} skeletonRows={5}
        empty={!error && <EmptyState icon="≡" title="No transactions" hint="Nothing matches this filter." />}
      />
    </Card>
  )
}

export default function Logs() {
  const [tab, setTab] = useState('activity')
  return (
    <div className="stack">
      <PageHeader
        title="Activity"
        subtitle="Task results as they happen, and the on-chain transactions behind them (with errors and explorer links)."
        actions={<Segmented value={tab} onChange={setTab} options={[{ value: 'activity', label: 'Task activity' }, { value: 'tx', label: 'Transactions' }]} />}
      />
      {tab === 'activity' ? <ActivityTab /> : <TransactionsTab />}
    </div>
  )
}
