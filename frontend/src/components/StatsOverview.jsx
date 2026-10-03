import React from 'react'
import api from '../api'
import useApi from '../hooks/useApi'
import { Card, Badge, EmptyState, StatTile, DataTable } from './ui'

const fmt = n => (n == null ? '—' : Number(n).toLocaleString())

function Chips({ data }) {
  const entries = Object.entries(data || {})
  if (!entries.length) return <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>none</span>
  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
      {entries.map(([k, n]) => <span key={k} className="badge neutral">{k}: {n}</span>)}
    </div>
  )
}

function ago(iso) {
  if (!iso) return '—'
  const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`)
  const m = Math.floor((Date.now() - d.getTime()) / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  if (m < 1440) return `${Math.floor(m / 60)}h ago`
  return `${Math.floor(m / 1440)}d ago`
}

export default function StatsOverview() {
  const { data: d, error: err, reload } = useApi(() => api.get('/stats/overview').then(r => r.data), [], { interval: 60000 })

  if (err && !d) {
    return (
      <Card title="Overview" action={<button className="sm" onClick={reload}>Retry</button>}>
        <p className="error">Could not load stats: {err}</p>
      </Card>
    )
  }
  if (!d) return <Card title="Overview"><div className="skeleton" style={{ height: 70, borderRadius: 10 }} /></Card>

  const t24 = d.transactions.last_24h, t7 = d.transactions.last_7d, all = d.transactions.all_time
  const sr = x => (x.success_rate == null ? '—' : `${x.success_rate}%`)

  return (
    <div className="stack">
      <div className="grid-stats">
        <Card><StatTile label="Projects" value={d.projects.total} sub={`${d.projects.by_status.active || 0} active`} /></Card>
        <Card><StatTile label="Wallets" value={d.wallets.total} tone="violet" sub={`${d.wallets.by_status.active || 0} active · ${d.wallets.gas_wallets} gas`} /></Card>
        <Card><StatTile label="Tx 24h" value={fmt(t24.total)} tone="signal" sub={`${sr(t24)} success · ${t24.gas_native_text} gas`} /></Card>
        <Card><StatTile label="Tx 7d" value={fmt(t7.total)} sub={`${sr(t7)} success · ${t7.gas_native_text} gas`} /></Card>
        <Card><StatTile label="All time" value={fmt(all.total)} sub={`${sr(all)} success · ${all.gas_native_text} gas`} /></Card>
        <Card><StatTile label="Open alerts" value={d.alerts_unresolved} tone={d.alerts_unresolved ? 'amber' : 'default'}
          sub={d.ai ? `${d.ai.pending_suggestions} AI suggestion(s)` : undefined} /></Card>
      </div>

      <div className="grid">
        <Card title="Projects by status"><Chips data={d.projects.by_status} /></Card>
        <Card title="Eligibility">
          <Chips data={d.projects.by_eligibility} />
          {d.projects.estimated_value_usd > 0 && (
            <p style={{ fontSize: 12.5, color: 'var(--text-dim)', marginBottom: 0 }}>
              Declared value of eligible projects: <span className="mono">${fmt(d.projects.estimated_value_usd)}</span>
            </p>
          )}
        </Card>
      </div>

      <Card title="Per-project rollup">
        {d.per_project.length === 0 ? (
          <EmptyState icon="◫" title="No projects yet" hint="Add a project to see its numbers here." />
        ) : (
          <DataTable
            rows={d.per_project}
            rowStyle={p => (p.status === 'archived' ? { opacity: 0.55 } : undefined)}
            columns={[
              { key: 'name', label: 'Project', render: p => <span style={{ fontWeight: 600 }}>{p.name}</span> },
              { key: 'status', label: 'Status', render: p => <Badge status={p.status}>{p.status}</Badge> },
              {
                key: 'elig', label: 'Eligibility',
                render: p => (
                  <Badge status={p.eligibility_status === 'eligible' ? 'success' : p.eligibility_status === 'not_eligible' ? 'failed' : 'neutral'}>
                    {p.eligibility_status}{p.eligibility_value_usd ? ` · $${Number(p.eligibility_value_usd).toFixed(0)}` : ''}
                  </Badge>
                ),
              },
              { key: 'tasks', label: 'Tasks', render: p => <span className="mono">{p.tasks_enabled}/{p.tasks_total}</span> },
              { key: 'tx', label: 'Tx ok / fail', num: true, render: p => <span className="mono">{p.tx_confirmed} / {p.tx_failed}</span> },
              { key: 'wallets', label: 'Wallets', num: true, render: p => <span className="mono">{p.wallets}</span> },
              { key: 'days', label: 'Active days', num: true, render: p => <span className="mono">{p.active_days}</span> },
              { key: 'gas', label: 'Gas', num: true, render: p => <span className="mono">{p.gas_native_text}</span> },
              { key: 'last', label: 'Last tx', render: p => <span className="faint" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>{ago(p.last_tx_at)}</span> },
            ]}
          />
        )}
      </Card>
    </div>
  )
}
