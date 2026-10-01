import React, { useEffect, useState } from 'react'
import api from '../api'
import { Card, Badge, EmptyState, StatTile } from './ui'

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
  const [d, setD] = useState(null)
  const [err, setErr] = useState(false)

  useEffect(() => {
    const load = () => api.get('/stats/overview').then(r => { setD(r.data); setErr(false) }).catch(() => setErr(true))
    load()
    const t = setInterval(load, 60000)
    return () => clearInterval(t)
  }, [])

  if (err && !d) return <Card title="Overview"><p className="error">Could not load stats.</p></Card>
  if (!d) return <Card title="Overview"><div className="skeleton" style={{ height: 70, borderRadius: 10 }} /></Card>

  const t24 = d.transactions.last_24h, t7 = d.transactions.last_7d, all = d.transactions.all_time
  const sr = x => (x.success_rate == null ? '—' : `${x.success_rate}%`)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 16 }}>
        <Card><StatTile label="Projects" value={d.projects.total} sub={`${d.projects.by_status.active || 0} active`} /></Card>
        <Card><StatTile label="Wallets" value={d.wallets.total} tone="violet" sub={`${d.wallets.by_status.active || 0} active · ${d.wallets.gas_wallets} gas`} /></Card>
        <Card><StatTile label="Tx 24h" value={fmt(t24.total)} tone="signal" sub={`${sr(t24)} success · $${t24.gas_usd} gas`} /></Card>
        <Card><StatTile label="Tx 7d" value={fmt(t7.total)} sub={`${sr(t7)} success · $${t7.gas_usd} gas`} /></Card>
        <Card><StatTile label="All time" value={fmt(all.total)} sub={`${sr(all)} success · $${all.gas_usd} gas`} /></Card>
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
          <div className="table-scroll"><table>
            <thead><tr>
              <th>Project</th><th>Status</th><th>Eligibility</th><th>Tasks</th>
              <th style={{ textAlign: 'right' }}>Tx ok / fail</th><th style={{ textAlign: 'right' }}>Wallets</th>
              <th style={{ textAlign: 'right' }}>Active days</th><th style={{ textAlign: 'right' }}>Gas $</th><th>Last tx</th>
            </tr></thead>
            <tbody>
              {d.per_project.map(p => (
                <tr key={p.id} style={{ opacity: p.status === 'archived' ? 0.55 : 1 }}>
                  <td style={{ fontWeight: 600 }}>{p.name}</td>
                  <td><Badge status={p.status === 'active' ? 'active' : p.status === 'stopped' || p.status === 'archived' ? 'failed' : p.status}>{p.status}</Badge></td>
                  <td>
                    <Badge status={p.eligibility_status === 'eligible' ? 'success' : p.eligibility_status === 'not_eligible' ? 'failed' : 'neutral'}>
                      {p.eligibility_status}{p.eligibility_value_usd ? ` · $${Number(p.eligibility_value_usd).toFixed(0)}` : ''}
                    </Badge>
                  </td>
                  <td className="mono">{p.tasks_enabled}/{p.tasks_total}</td>
                  <td className="mono" style={{ textAlign: 'right' }}>{p.tx_confirmed} / {p.tx_failed}</td>
                  <td className="mono" style={{ textAlign: 'right' }}>{p.wallets}</td>
                  <td className="mono" style={{ textAlign: 'right' }}>{p.active_days}</td>
                  <td className="mono" style={{ textAlign: 'right' }}>${p.gas_usd}</td>
                  <td style={{ fontSize: 12, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>{ago(p.last_tx_at)}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </Card>
    </div>
  )
}
