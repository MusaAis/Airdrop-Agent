import React, { useEffect, useState } from 'react'
import api from '../api'
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

// Discovery status/runs were removed along with the discovery/scraping
// system (see PLAN.md §3) — projects are now submitted manually only.
// This page now shows AI validations only (risk/config/criteria/gap/sybil
// checks run against manually-added projects).
export default function AiLog({ token }) {
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(false)
  const [initialLoad, setInitialLoad] = useState(true)
  const [selected, setSelected] = useState(null)
  const [errorMsg, setErrorMsg] = useState('')

  const load = async () => {
    setLoading(true)
    setErrorMsg('')
    try {
      const valRes = await api.get('/ai/validations', { params: { limit: 50 } })
      setEntries(Array.isArray(valRes.data) ? valRes.data : [])
    } catch (e) {
      setErrorMsg('Could not load AI log — check that you are logged in and the backend is reachable.')
      console.error(e)
    } finally {
      setLoading(false)
      setInitialLoad(false)
    }
  }

  useEffect(() => { load() }, [])

  const resolve = async (id, decision) => {
    try {
      await api.post(`/ai/validations/${id}/resolve`, null, { params: { human_decision: decision } })
      load()
    } catch (e) {
      setErrorMsg(`Error resolving validation ${id}`)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <Card title="AI Validations">
        <p style={{ fontSize: 12.5, color: 'var(--text-dim)', marginTop: -8, marginBottom: 14 }}>
          Risk, config, criteria, gap, and Sybil checks run by the dual-AI validator against manually-added projects and wallets.
        </p>
        {errorMsg && <div style={{ fontSize: 13, color: 'var(--rose)', marginBottom: 12 }}>{errorMsg}</div>}
        {initialLoad ? (
          <div className="table-scroll"><table><tbody><SkeletonRows rows={5} cols={5} /></tbody></table></div>
        ) : entries.length === 0 ? (
          <EmptyState icon="◇" title="No validations yet" hint="Validations appear here once you approve a project, run a gap check, or trigger one manually via /ai/validate." />
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
