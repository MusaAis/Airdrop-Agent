import React, { useState } from 'react'
import api from '../api'
import useApi, { apiError } from '../hooks/useApi'
import { useToast } from '../components/Toast'
import { Card, PageHeader, Badge, Segmented, EmptyState, SkeletonBlock } from '../components/ui'
import { fmtDateTime } from '../lib/format'

const SEV_TONE = { critical: 'danger', warning: 'warning', info: 'success' }
const SEV_COLOR = { critical: 'var(--rose)', warning: 'var(--amber)', info: 'var(--signal)' }

export default function Notifications() {
  const toast = useToast()
  const [filter, setFilter] = useState('unresolved')
  const [busy, setBusy] = useState(false)

  const alerts = useApi(() => api.get('/agent/alerts-list').then(r => r.data), [], { interval: 30000 })
  const snooze = useApi(() => api.get('/agent/alerts/snooze').then(r => r.data), [], { interval: 30000 })

  const list = Array.isArray(alerts.data) ? alerts.data : []
  const snoozedUntil = snooze.data?.snoozed ? snooze.data.until : null
  const unresolved = list.filter(a => !a.resolved).length

  const run = async (fn, ok) => {
    setBusy(true)
    try { await fn(); if (ok) toast.success(ok); await Promise.all([alerts.reload(), snooze.reload()]) }
    catch (e) { toast.error(apiError(e)) }
    finally { setBusy(false) }
  }

  const visible = list.filter(a =>
    filter === 'all' ? true : filter === 'unresolved' ? !a.resolved : a.severity === filter)

  return (
    <div className="stack">
      <PageHeader
        title="Alerts"
        subtitle="Everything the agent flags is recorded here, even when Telegram is snoozed."
        actions={
          <>
            <button onClick={() => { alerts.reload(); snooze.reload() }} disabled={alerts.refreshing}>Refresh</button>
            {unresolved > 0 && <button className="primary" disabled={busy} onClick={() => run(() => api.post('/agent/alerts/resolve-all'), 'All alerts resolved.')}>Resolve all ({unresolved})</button>}
          </>
        }
      />

      <Card tight>
        <div className="row-between">
          <div style={{ fontSize: 13 }}>
            {snoozedUntil
              ? <>🔕 Telegram snoozed until <strong>{fmtDateTime(snoozedUntil)}</strong> <span className="faint">· critical alerts still go out</span></>
              : <>🔔 Telegram alerts are on</>}
          </div>
          <div className="row">
            {snoozedUntil
              ? <button className="sm" disabled={busy} onClick={() => run(() => api.delete('/agent/alerts/snooze'), 'Alerts resumed.')}>Resume now</button>
              : [30, 120, 480].map(m => (
                <button key={m} className="sm" disabled={busy} onClick={() => run(() => api.post('/agent/alerts/snooze', null, { params: { minutes: m } }), `Snoozed for ${m >= 60 ? `${m / 60}h` : `${m}m`}.`)}>
                  Snooze {m >= 60 ? `${m / 60}h` : `${m}m`}
                </button>
              ))}
          </div>
        </div>
      </Card>

      <Segmented value={filter} onChange={setFilter} options={['unresolved', 'all', 'critical', 'warning', 'info']} />

      {alerts.error && <div className="error">{alerts.error}</div>}

      {alerts.loading ? <SkeletonBlock height={100} /> : visible.length === 0 ? (
        <Card><EmptyState icon="✓" title={filter === 'unresolved' ? 'All clear' : 'Nothing here'} hint={filter === 'unresolved' ? 'No unresolved alerts.' : 'No alerts match this filter.'} /></Card>
      ) : (
        <div className="stack-sm">
          {visible.map(a => (
            <div key={a.id} className="card tight" style={{ opacity: a.resolved ? 0.55 : 1, borderLeft: `3px solid ${SEV_COLOR[a.severity] || 'var(--border)'}` }}>
              <div className="row-between" style={{ alignItems: 'flex-start', flexWrap: 'nowrap' }}>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div className="row" style={{ gap: 8, marginBottom: 6 }}>
                    <Badge tone={SEV_TONE[a.severity] || 'neutral'}>{a.severity}</Badge>
                    <span style={{ fontWeight: 600, fontSize: 13 }}>{a.type?.replace(/_/g, ' ')}</span>
                    {a.resolved && <span className="faint" style={{ fontSize: 11 }}>resolved</span>}
                  </div>
                  <div className="muted" style={{ fontSize: 13, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{a.message}</div>
                  <div className="faint" style={{ fontSize: 11, marginTop: 6 }}>{fmtDateTime(a.created_at)}</div>
                </div>
                {!a.resolved && <button className="sm" disabled={busy} onClick={() => run(() => api.post(`/agent/alerts/${a.id}/resolve`))}>Resolve</button>}
              </div>
            </div>
          ))}
          {list.length >= 50 && <p className="hint" style={{ textAlign: 'center' }}>Showing the latest 50 alerts.</p>}
        </div>
      )}
    </div>
  )
}
