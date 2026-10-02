import React, { useMemo } from 'react'
import { Link } from 'react-router-dom'
import api from '../api'
import useApi from '../hooks/useApi'
import { Card, PageHeader, StatTile, EmptyState, SkeletonBlock, Badge, Meter } from '../components/ui'

const DAY = 86400000
const toneFor = d => (d <= 0 ? 'var(--text-faint)' : d <= 7 ? 'var(--rose)' : d <= 30 ? 'var(--amber)' : 'var(--signal)')

export default function Snapshot() {
  const { data, loading, error, reload, refreshing } = useApi(() => api.get('/projects/').then(r => r.data), [])

  const rows = useMemo(() => {
    const startOfToday = new Date(); startOfToday.setHours(0, 0, 0, 0)
    return (Array.isArray(data) ? data : [])
      .filter(p => p.airdrop_date || p.tge_date)
      .map(p => {
        const date = p.airdrop_date || p.tge_date
        // dates are plain YYYY-MM-DD: compare as local calendar days, not UTC instants
        const [y, m, d] = String(date).slice(0, 10).split('-').map(Number)
        const days = Math.round((new Date(y, m - 1, d) - startOfToday) / DAY)
        return { ...p, date, kind: p.airdrop_date ? 'Snapshot / airdrop' : 'TGE', days }
      })
      .sort((a, b) => (a.days <= 0) - (b.days <= 0) || a.days - b.days)
  }, [data])

  const upcoming = rows.filter(r => r.days > 0)
  const soon = upcoming.filter(r => r.days <= 7).length

  return (
    <div className="stack">
      <PageHeader
        title="Snapshot calendar"
        subtitle="Deadlines come from each project's airdrop or TGE date. Set them on the project page."
        actions={<button onClick={reload} disabled={refreshing}>{refreshing ? 'Refreshing…' : 'Refresh'}</button>}
      />
      {error && <div className="error">{error}</div>}

      <div className="grid-stats">
        <Card><StatTile label="With a date" value={loading ? '…' : rows.length} /></Card>
        <Card><StatTile label="Upcoming" value={loading ? '…' : upcoming.length} tone="violet" /></Card>
        <Card><StatTile label="Within 7 days" value={loading ? '…' : soon} tone={soon ? 'rose' : 'default'} /></Card>
      </div>

      {loading ? <SkeletonBlock height={120} /> : rows.length === 0 ? (
        <Card><EmptyState icon="▦" title="No deadlines set" hint="Add an airdrop or TGE date on a project and it will show up here." action={<Link to="/projects">Go to projects →</Link>} /></Card>
      ) : (
        <div className="stack-sm">
          {rows.map(p => (
            <Card key={p.id} tight style={{ opacity: p.days <= 0 ? 0.6 : 1 }}>
              <div className="row-between" style={{ marginBottom: 10 }}>
                <div style={{ minWidth: 0 }}>
                  <Link to={`/projects/${p.id}`} style={{ fontWeight: 600, fontSize: 14 }}>{p.name}</Link>
                  <div className="faint" style={{ fontSize: 12 }}>{p.kind} · {p.date}</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div className="mono" style={{ fontWeight: 700, fontSize: 16, color: toneFor(p.days) }}>
                    {p.days <= 0 ? 'Passed' : p.days === 1 ? 'Tomorrow' : `${p.days}d`}
                  </div>
                  {p.days > 0 && <div className="faint" style={{ fontSize: 11 }}>left</div>}
                </div>
              </div>
              <Meter percent={p.days <= 0 ? 100 : 100 - Math.min(p.days, 90) / 90 * 100} tone={toneFor(p.days)} />
              <div className="row" style={{ marginTop: 10, gap: 8 }}>
                <Badge status={p.status}>{p.status}</Badge>
                <span className="chip">priority {p.priority}</span>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
