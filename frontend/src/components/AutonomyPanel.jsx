import React, { useEffect, useState, useCallback } from 'react'
import api from '../api'
import { Card, Badge, EmptyState } from './ui'

const TYPE_LABEL = {
  wallet_pause: 'Wallet pause',
  gas_multiplier: 'Gas multiplier',
  task_disable: 'Task disable',
  project_priority: 'Project priority',
}

function timeAgo(iso) {
  if (!iso) return '—'
  // server stores naive UTC; make sure the browser reads it as UTC
  const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`)
  const mins = Math.floor((Date.now() - d.getTime()) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function statusLabel(a) {
  if (a.status === 'reverted') return a.reverted_by === 'auto' ? 'auto-reverted' : 'undone'
  return a.status
}

export default function AutonomyPanel() {
  const [summary, setSummary] = useState(null)
  const [actions, setActions] = useState([])
  const [loaded, setLoaded] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [open, setOpen] = useState(null)

  const load = useCallback(async () => {
    try {
      const [s, a] = await Promise.all([
        api.get('/autonomy/status'),
        api.get('/autonomy/actions', { params: { limit: 30 } }),
      ])
      setSummary(s.data)
      setActions(Array.isArray(a.data) ? a.data : [])
    } catch (e) {
      setMessage('Could not load AI autonomy state. Check that you are logged in and the backend is reachable.')
    } finally {
      setLoaded(true)
    }
  }, [])

  useEffect(() => {
    load()
    const t = setInterval(load, 30000)
    return () => clearInterval(t)
  }, [load])

  const toggleFreeze = async () => {
    setBusy(true)
    setMessage('')
    try {
      const r = await api.post(summary?.paused ? '/autonomy/resume' : '/autonomy/pause')
      setSummary(r.data)
    } catch (e) {
      setMessage('Could not change the freeze switch.')
    } finally {
      setBusy(false)
    }
  }

  const act = async (id, verb) => {
    setBusy(true)
    setMessage('')
    try {
      const r = await api.post(`/autonomy/actions/${id}/${verb}`)
      setMessage(r.data.message || 'Done.')
      await load()
    } catch (e) {
      setMessage(e?.response?.data?.detail || 'Action failed.')
    } finally {
      setBusy(false)
    }
  }

  const paused = !!summary?.paused
  const counts = summary?.last_24h || {}

  return (
    <Card
      title="AI autonomy"
      action={
        summary && (
          <button className={paused ? 'primary sm' : 'sm danger'} onClick={toggleFreeze} disabled={busy}>
            {paused ? 'Resume autonomy' : 'Freeze autonomy'}
          </button>
        )
      }
    >
      <p style={{ fontSize: 12.5, color: 'var(--text-dim)', marginTop: -8, marginBottom: 14 }}>
        The AI can pause wallets, nudge gas multipliers (0.7×–1.8×, 0.1 per step), disable failing tasks and
        lower a failing project's priority. Every change is logged, sent to Telegram and reversible. It can never
        add projects or tasks, touch keys, or execute claims.
      </p>

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', marginBottom: 14 }}>
        <Badge status={paused ? 'failed' : 'active'}>{paused ? 'frozen' : 'active'}</Badge>
        {summary?.emergency_stop && <Badge status="failed">emergency stop</Badge>}
        <span style={{ fontSize: 12.5, color: 'var(--text-dim)' }}>
          last 24h: {Object.keys(counts).length
            ? Object.entries(counts).map(([k, n]) => `${n} ${k}`).join(' · ')
            : 'no activity'}
        </span>
        {summary?.pending_suggestions > 0 && (
          <Badge status="pending">{summary.pending_suggestions} awaiting your approval</Badge>
        )}
      </div>

      {message && <div style={{ fontSize: 13, color: 'var(--text-dim)', marginBottom: 12 }}>{message}</div>}

      {!loaded ? (
        <div className="skeleton" style={{ height: 60, borderRadius: 10 }} />
      ) : actions.length === 0 ? (
        <EmptyState
          icon="◇"
          title="No autonomous actions yet"
          hint="Actions appear here when failure clusters give the AI a reason to act."
        />
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr><th>When</th><th>Action</th><th>Status</th><th style={{ textAlign: 'right' }}></th></tr>
            </thead>
            <tbody>
              {actions.map(a => (
                <React.Fragment key={a.id}>
                  <tr style={{ cursor: 'pointer' }} onClick={() => setOpen(open === a.id ? null : a.id)}>
                    <td style={{ fontSize: 12, color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>{timeAgo(a.created_at)}</td>
                    <td>
                      <div style={{ fontWeight: 600, fontSize: 13 }}>A{a.id} · {TYPE_LABEL[a.action_type] || a.action_type}</div>
                      <div style={{ fontSize: 12.5, color: 'var(--text-dim)' }}>{a.summary}</div>
                    </td>
                    <td>
                      <Badge status={a.status === 'applied' ? 'success' : a.status === 'suggested' ? 'pending' : a.status === 'failed' ? 'failed' : 'neutral'}>
                        {statusLabel(a)}
                      </Badge>
                    </td>
                    <td style={{ textAlign: 'right' }} onClick={e => e.stopPropagation()}>
                      <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                        {a.status === 'suggested' && (
                          <>
                            <button className="primary sm" disabled={busy} onClick={() => act(a.id, 'approve')}>Approve</button>
                            <button className="sm" disabled={busy} onClick={() => act(a.id, 'undo')}>Dismiss</button>
                          </>
                        )}
                        {a.status === 'applied' && a.reversible && (
                          <button className="sm" disabled={busy} onClick={() => act(a.id, 'undo')}>Undo</button>
                        )}
                      </div>
                    </td>
                  </tr>
                  {open === a.id && (
                    <tr style={{ background: 'var(--bg)' }}>
                      <td colSpan={4}>
                        <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 8, fontSize: 12.5 }}>
                          <div><span style={{ color: 'var(--text-faint)' }}>Why: </span>{a.reason}</div>
                          {a.ai_reasoning && (
                            <div>
                              <span style={{ color: 'var(--text-faint)' }}>AI review{a.agreement_score != null ? ` (${a.agreement_score}% agreement)` : ''}: </span>
                              {a.ai_reasoning}
                            </div>
                          )}
                          {(a.before || a.after) && (
                            <div className="mono" style={{ color: 'var(--text-dim)' }}>
                              {JSON.stringify(a.before)} → {JSON.stringify(a.after)}
                            </div>
                          )}
                          {a.error && <div className="error">{a.error}</div>}
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}
