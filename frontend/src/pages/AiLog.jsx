import React, { useEffect, useState } from 'react'
import api from '../api'
import Spinner from '../components/Spinner'
import { Card, Badge, EmptyState, SkeletonRows } from '../components/ui'

function timeAgo(iso) {
  if (!iso) return '—'
  const diffMs = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diffMs / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

export default function AiLog({ token }) {
  const [entries, setEntries] = useState([])
  const [runs, setRuns] = useState([])
  const [nextRun, setNextRun] = useState(null)
  const [loading, setLoading] = useState(false)
  const [initialLoad, setInitialLoad] = useState(true)
  const [triggering, setTriggering] = useState(false)
  const [selected, setSelected] = useState(null)
  const [errorMsg, setErrorMsg] = useState('')

  const load = async () => {
    setLoading(true)
    setErrorMsg('')
    try {
      const [valRes, runsRes, nextRes] = await Promise.all([
        api.get('/ai/validations', { params: { limit: 50 } }),
        api.get('/ai/discovery/runs', { params: { limit: 10 } }),
        api.get('/ai/discovery/next-run'),
      ])
      setEntries(Array.isArray(valRes.data) ? valRes.data : [])
      setRuns(Array.isArray(runsRes.data) ? runsRes.data : [])
      setNextRun(nextRes.data?.next_run_at || null)
    } catch (e) {
      // Previously every fetch failure here was silently swallowed by a bare
      // catch {}, which made the page show "No validations yet." even when
      // the real problem was an auth error or the server being down —
      // indistinguishable from "discovery genuinely hasn't found anything."
      setErrorMsg('Could not load AI log — check that you are logged in and the backend is reachable.')
      console.error(e)
    } finally {
      setLoading(false)
      setInitialLoad(false)
    }
  }

  useEffect(() => { load() }, [])

  const triggerDiscovery = async () => {
    setTriggering(true)
    try {
      await api.post('/ai/discovery/run-now')
      await load()
    } catch (e) {
      setErrorMsg('Error triggering discovery scan')
    } finally {
      setTriggering(false)
    }
  }

  const resolve = async (id, decision) => {
    // Previously called POST /ai/validations/{id}/approve and /reject, which
    // do not exist on the backend (the real route is /resolve with a
    // human_decision param) — these buttons silently 404'd every time.
    try {
      await api.post(`/ai/validations/${id}/resolve`, null, { params: { human_decision: decision } })
      load()
    } catch (e) {
      setErrorMsg(`Error resolving validation ${id}`)
    }
  }

  const lastRun = runs[0]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <Card title="Discovery Status">
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: 11, color: 'var(--text-faint)', textTransform: 'uppercase' }}>Last run</div>
            <div style={{ fontSize: 15, fontWeight: 600 }}>
              {lastRun ? (
                <>
                  {timeAgo(lastRun.finished_at || lastRun.started_at)}{' '}
                  <Badge status={lastRun.status === 'success' ? 'active' : lastRun.status === 'running' ? 'pending' : 'failed'}>
                    {lastRun.status}
                  </Badge>
                </>
              ) : 'never run yet'}
            </div>
          </div>
          {lastRun && lastRun.status === 'success' && (
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-faint)', textTransform: 'uppercase' }}>Found / Validated</div>
              <div style={{ fontSize: 15, fontWeight: 600 }}>
                {lastRun.raw_results_found ?? '—'} found, {lastRun.new_projects_validated ?? '—'} validated
              </div>
            </div>
          )}
          {lastRun && lastRun.status === 'failed' && (
            <div>
              <div style={{ fontSize: 11, color: 'var(--rose)', textTransform: 'uppercase' }}>Error</div>
              <div style={{ fontSize: 13, color: 'var(--rose)' }}>{lastRun.error_message}</div>
            </div>
          )}
          <div>
            <div style={{ fontSize: 11, color: 'var(--text-faint)', textTransform: 'uppercase' }}>Next scheduled run</div>
            <div style={{ fontSize: 15, fontWeight: 600 }}>{nextRun ? new Date(nextRun).toLocaleString() : '—'}</div>
          </div>
          <button className="primary" onClick={triggerDiscovery} disabled={triggering} style={{ marginLeft: 'auto' }}>
            {triggering ? <Spinner inline size={14} /> : 'Run Discovery Now'}
          </button>
        </div>
      </Card>

      <Card title="Recent Discovery Runs">
        {initialLoad ? (
          <div className="table-scroll"><table><tbody><SkeletonRows rows={3} cols={5} /></tbody></table></div>
        ) : runs.length === 0 ? (
          <EmptyState icon="◇" title="No discovery runs recorded yet" hint="Click 'Run Discovery Now' above, or wait for the scheduled scan." />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr><th>When</th><th>Trigger</th><th>Status</th><th>Found</th><th>Validated</th></tr>
              </thead>
              <tbody>
                {runs.map(r => (
                  <tr key={r.id}>
                    <td>{timeAgo(r.started_at)}</td>
                    <td><Badge status="pending">{r.trigger}</Badge></td>
                    <td><Badge status={r.status === 'success' ? 'active' : r.status === 'running' ? 'pending' : 'failed'}>{r.status}</Badge></td>
                    <td>{r.raw_results_found ?? '—'}</td>
                    <td>{r.new_projects_validated ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="AI Validations">
        {errorMsg && <div style={{ fontSize: 13, color: 'var(--rose)', marginBottom: 12 }}>{errorMsg}</div>}
        {initialLoad ? (
          <div className="table-scroll"><table><tbody><SkeletonRows rows={5} cols={5} /></tbody></table></div>
        ) : entries.length === 0 ? (
          <EmptyState icon="◇" title="No validations yet" hint="Validations appear here once discovery finds a project, or you trigger one manually via /ai/validate." />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr><th>Type</th><th>Agreement</th><th>Needs Review</th><th>When</th><th></th></tr>
              </thead>
              <tbody>
                {entries.map(e => {
                  const isOpen = selected === e.id
                  return (
                    <React.Fragment key={e.id}>
                      <tr style={{ cursor: 'pointer' }} onClick={() => setSelected(isOpen ? null : e.id)}>
                        <td><Badge status="pending">{e.task_type}</Badge></td>
                        <td className="mono">{e.agreement_score}%</td>
                        <td>
                          {e.requires_human
                            ? <Badge status={e.resolved ? 'active' : 'failed'}>{e.resolved ? 'resolved' : 'needs review'}</Badge>
                            : <Badge status="active">auto-ok</Badge>}
                        </td>
                        <td style={{ fontSize: 12, color: 'var(--text-faint)' }}>{timeAgo(e.created_at)}</td>
                        <td>{isOpen ? '▲' : '▼'}</td>
                      </tr>
                      {isOpen && (
                        <tr style={{ background: 'var(--bg)' }}>
                          <td colSpan={5}>
                            <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
                              {e.conflict_fields && Object.keys(e.conflict_fields || {}).length > 0 && (
                                <div>
                                  <div style={{ fontSize: 11, color: 'var(--text-faint)', textTransform: 'uppercase', marginBottom: 4 }}>Conflicts</div>
                                  <pre className="mono" style={{ fontSize: 11.5, whiteSpace: 'pre-wrap' }}>{JSON.stringify(e.conflict_fields, null, 2)}</pre>
                                </div>
                              )}
                              <div>
                                <div style={{ fontSize: 11, color: 'var(--text-faint)', textTransform: 'uppercase', marginBottom: 4 }}>Final Decision</div>
                                <pre className="mono" style={{ fontSize: 11.5, whiteSpace: 'pre-wrap' }}>{JSON.stringify(e.final_decision, null, 2)}</pre>
                              </div>
                              {e.requires_human && !e.resolved && (
                                <div style={{ display: 'flex', gap: 8 }}>
                                  <button className="primary sm" onClick={() => resolve(e.id, 'approved')}>Approve</button>
                                  <button className="sm danger" onClick={() => resolve(e.id, 'rejected')}>Reject</button>
                                </div>
                              )}
                              {e.resolved && (
                                <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>
                                  Resolved: <Badge status={e.human_decision === 'approved' ? 'active' : 'failed'}>{e.human_decision}</Badge>
                                </div>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
