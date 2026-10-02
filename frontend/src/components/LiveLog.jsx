import React from 'react'
import { Badge, EmptyState } from './ui'
import { fmtTime } from '../lib/format'

/** Formatted view of live Log events (newest first). */
export default function LiveLog({ events, maxHeight = 320 }) {
  if (!events.length) {
    return <EmptyState icon="◌" title="Waiting for activity" hint="Log entries stream in here as the agent works." />
  }
  return (
    <div className="card flat tight" style={{ maxHeight, overflowY: 'auto', padding: 0 }}>
      {events.map((l, i) => (
        <div key={l.id ?? i} style={{ padding: '10px 14px', borderBottom: '1px solid var(--border-soft)' }}>
          <div className="row" style={{ gap: 8 }}>
            <span className="mono faint" style={{ fontSize: 11.5 }}>{fmtTime(l.created_at)}</span>
            <Badge status={l.status}>{l.status}</Badge>
            <span style={{ fontWeight: 600, fontSize: 13 }}>{l.task_name || 'task'}</span>
            {l.wallet_id != null && <span className="chip">wallet #{l.wallet_id}</span>}
            {l.is_dry_run && <span className="chip">dry-run</span>}
          </div>
          {l.error_message && <div className="muted" style={{ fontSize: 12, marginTop: 4, overflowWrap: 'anywhere' }}>{l.error_message}</div>}
          {l.tx_hash && <div className="mono faint" style={{ fontSize: 11, marginTop: 2, overflowWrap: 'anywhere' }}>{l.tx_hash}</div>}
        </div>
      ))}
    </div>
  )
}
