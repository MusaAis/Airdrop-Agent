import React, { useState } from 'react'
import api from '../api'
import useApi, { apiError } from '../hooks/useApi'
import { useToast } from '../components/Toast'
import { Card, Badge, PageHeader, EmptyState, DataTable } from '../components/ui'
import { timeAgo } from '../lib/format'

// Discovery was removed (PLAN.md §3) — this page shows AI validations only: the dual-AI
// risk / config / criteria / gap / sybil checks run against manually added projects.
export default function AiLog() {
  const toast = useToast()
  const { data, loading, error, reload, refreshing } = useApi(() => api.get('/ai/validations', { params: { limit: 50 } }).then(r => r.data), [])
  const entries = Array.isArray(data) ? data : []
  const [selected, setSelected] = useState(null)
  const [busy, setBusy] = useState(false)

  const resolve = async (id, decision) => {
    setBusy(true)
    try {
      await api.post(`/ai/validations/${id}/resolve`, null, { params: { human_decision: decision } })
      toast.success(`Validation ${id} ${decision}.`)
      await reload()
    } catch (e) { toast.error(apiError(e, `Could not resolve validation ${id}.`)) }
    finally { setBusy(false) }
  }

  const columns = [
    { key: 'type', label: 'Type', render: e => <Badge tone="warning">{e.task_type}</Badge> },
    { key: 'agree', label: 'Agreement', num: true, render: e => <span className="mono">{e.agreement_score}%</span> },
    {
      key: 'review', label: 'Review',
      render: e => e.requires_human
        ? <Badge tone={e.resolved ? 'success' : 'danger'}>{e.resolved ? 'resolved' : 'needs review'}</Badge>
        : <Badge tone="success">auto-ok</Badge>,
    },
    { key: 'when', label: 'When', render: e => <span className="faint" style={{ fontSize: 12 }}>{timeAgo(e.created_at)}</span> },
    { key: 'caret', label: '', render: e => <span className="muted">{selected === e.id ? '▲' : '▼'}</span> },
  ]

  return (
    <div className="stack">
      <PageHeader
        title="AI validations"
        subtitle="Risk, config, criteria, gap and Sybil checks by the dual-AI validator. Tap a row to see the reasoning."
        actions={<button onClick={reload} disabled={refreshing}>{refreshing ? 'Refreshing…' : 'Refresh'}</button>}
      />
      {error && <div className="error">{error}</div>}
      <Card>
        <DataTable
          columns={columns} rows={entries} loading={loading} skeletonRows={5}
          onRowClick={e => setSelected(s => (s === e.id ? null : e.id))}
          expanded={selected}
          renderExpanded={e => (
            <div className="stack-sm" style={{ padding: 8 }}>
              {e.conflict_fields && Object.keys(e.conflict_fields).length > 0 && (
                <div>
                  <div className="eyebrow" style={{ marginBottom: 4 }}>Conflicts</div>
                  <pre className="mono" style={{ fontSize: 11.5, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{JSON.stringify(e.conflict_fields, null, 2)}</pre>
                </div>
              )}
              <div>
                <div className="eyebrow" style={{ marginBottom: 4 }}>Final decision</div>
                <pre className="mono" style={{ fontSize: 11.5, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{JSON.stringify(e.final_decision, null, 2)}</pre>
              </div>
              {e.requires_human && !e.resolved && (
                <div className="row">
                  <button className="primary sm" disabled={busy} onClick={ev => { ev.stopPropagation(); resolve(e.id, 'approved') }}>Approve</button>
                  <button className="sm danger" disabled={busy} onClick={ev => { ev.stopPropagation(); resolve(e.id, 'rejected') }}>Reject</button>
                </div>
              )}
              {e.resolved && (
                <div className="muted" style={{ fontSize: 12 }}>
                  Resolved: <Badge tone={e.human_decision === 'approved' ? 'success' : 'danger'}>{e.human_decision}</Badge>
                </div>
              )}
            </div>
          )}
          empty={<EmptyState icon="◇" title="No validations yet" hint="They appear once you approve a project, run a gap check, or trigger one via /ai/validate." />}
        />
      </Card>
    </div>
  )
}
