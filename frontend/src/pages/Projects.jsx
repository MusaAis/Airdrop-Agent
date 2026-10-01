import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../api'
import { Card, Badge, EmptyState } from '../components/ui'

function EligibilityBadge({ project }) {
  if (project.eligibility_status === 'eligible') {
    const val = project.eligibility_value_usd
    return <Badge status="success">Eligible{val ? ` · $${Number(val).toFixed(2)}` : ''}</Badge>
  }
  if (project.eligibility_status === 'not_eligible') {
    return <Badge status="failed">Not eligible</Badge>
  }
  return <Badge status="neutral">Pending</Badge>
}

function EligibilityModal({ project, onClose, onSaved }) {
  const [choice, setChoice] = useState('eligible')
  const [value, setValue] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const save = async () => {
    setError('')
    setSaving(true)
    try {
      await api.post(`/projects/${project.id}/eligibility`, {
        eligible: choice === 'eligible',
        value_usd: choice === 'eligible' && value ? parseFloat(value) : null,
      })
      onSaved()
    } catch (e) {
      setError(e?.response?.data?.detail || 'Could not save eligibility.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 50,
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20,
    }}>
      <div className="card" style={{ maxWidth: 420, width: '100%' }}>
        <h3 style={{ fontSize: 15, marginBottom: 4 }}>Declare eligibility — {project.name}</h3>
        <p style={{ fontSize: 12.5, color: 'var(--text-dim)', marginTop: 0, marginBottom: 16 }}>
          This stops the agent from scheduling any further tasks for this project, whether it's
          eligible or not. You can clear this later if it was a mistake.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13.5 }}>
            <input type="radio" name="elig" checked={choice === 'eligible'} onChange={() => setChoice('eligible')} style={{ width: 'auto' }} />
            Eligible
          </label>
          {choice === 'eligible' && (
            <input
              placeholder="Estimated airdrop value in USD (optional)"
              type="number" step="any"
              value={value}
              onChange={e => setValue(e.target.value)}
              style={{ marginLeft: 24 }}
            />
          )}
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13.5 }}>
            <input type="radio" name="elig" checked={choice === 'not_eligible'} onChange={() => setChoice('not_eligible')} style={{ width: 'auto' }} />
            Not eligible
          </label>
        </div>
        {error && <div className="error" style={{ marginTop: 12 }}>{error}</div>}
        <div style={{ display: 'flex', gap: 10, marginTop: 18, justifyContent: 'flex-end' }}>
          <button className="ghost" onClick={onClose} disabled={saving}>Cancel</button>
          <button className="primary" onClick={save} disabled={saving}>
            {saving ? 'Saving…' : 'Declare'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function Projects() {
  const [projects, setProjects] = useState([])
  const [loaded, setLoaded] = useState(false)
  const [newProj, setNewProj] = useState({ name: '', type: 'dapp', chain_ids: '' })
  const [showArchived, setShowArchived] = useState(false)
  const [actionMessage, setActionMessage] = useState('')
  const [eligibilityTarget, setEligibilityTarget] = useState(null)

  const fetchProjects = () =>
    api.get('/projects/', { params: showArchived ? { include_archived: true } : {} })
      .then(r => { setProjects(r.data); setLoaded(true) })
      .catch(() => setLoaded(true))

  useEffect(() => { fetchProjects() }, [showArchived])

  const add = async () => {
    if (!newProj.name) return
    await api.post('/projects/', { ...newProj, chain_ids: newProj.chain_ids.split(',').map(Number).filter(n => !Number.isNaN(n)) })
    setNewProj({ name: '', type: 'dapp', chain_ids: '' })
    fetchProjects()
  }

  const archive = async (p) => {
    if (!window.confirm(`Archive "${p.name}"? It stays in your records and history — this just stops it from farming and hides it from the default list.`)) return
    setActionMessage('')
    try {
      const r = await api.delete(`/projects/${p.id}`)
      setActionMessage(r.data.message || 'Archived.')
      fetchProjects()
    } catch (e) {
      setActionMessage('Error archiving project.')
    }
  }

  const restore = async (p) => {
    setActionMessage('')
    try {
      await api.post(`/projects/${p.id}/restore`)
      fetchProjects()
    } catch (e) {
      setActionMessage('Error restoring project.')
    }
  }

  const stop = async (p) => {
    if (!window.confirm(`Stop "${p.name}"? This halts farming but keeps it visible (unlike archive).`)) return
    setActionMessage('')
    try {
      await api.post(`/projects/${p.id}/stop`)
      fetchProjects()
    } catch (e) {
      setActionMessage('Error stopping project.')
    }
  }

  const resume = async (p) => {
    setActionMessage('')
    try {
      await api.put(`/projects/${p.id}`, { status: 'active' })
      fetchProjects()
    } catch (e) {
      setActionMessage('Error resuming project.')
    }
  }

  const clearEligibility = async (p) => {
    if (!window.confirm(`Clear the eligibility declaration for "${p.name}"? Farming can resume once cleared.`)) return
    setActionMessage('')
    try {
      await api.post(`/projects/${p.id}/eligibility/clear`)
      fetchProjects()
    } catch (e) {
      setActionMessage('Error clearing eligibility.')
    }
  }

  const isDeclared = (p) => p.eligibility_status === 'eligible' || p.eligibility_status === 'not_eligible'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <Card
        title="Add project"
        action={
          <Link to="/projects/new" style={{ fontSize: 12.5, fontWeight: 600 }}>
            Guided setup →
          </Link>
        }
      >
        <p style={{ fontSize: 12.5, color: 'var(--text-dim)', marginTop: -8, marginBottom: 14 }}>
          Quick add below (name, type and chains only), or use guided setup for tasks and AI-drafted criteria.
        </p>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <input placeholder="Name" value={newProj.name} onChange={e => setNewProj({ ...newProj, name: e.target.value })} />
          <select value={newProj.type} onChange={e => setNewProj({ ...newProj, type: e.target.value })}>
            <option value="dapp">dApp</option>
            <option value="bridge">Bridge</option>
            <option value="lending">Lending</option>
            <option value="dex">DEX</option>
            <option value="other">Other</option>
          </select>
          <input placeholder="Chain IDs (comma sep)" value={newProj.chain_ids} onChange={e => setNewProj({ ...newProj, chain_ids: e.target.value })} style={{ minWidth: 180, flex: 1 }} />
          <button className="primary" onClick={add}>Add project</button>
        </div>
      </Card>

      {actionMessage && <div className="success">{actionMessage}</div>}

      <Card
        title="All projects"
        action={
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12.5, color: 'var(--text-dim)' }}>
            <input type="checkbox" checked={showArchived} onChange={e => setShowArchived(e.target.checked)} style={{ width: 'auto' }} />
            Show archived
          </label>
        }
      >
        {!loaded && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {Array.from({ length: 3 }).map((_, i) => <div key={i} className="skeleton" style={{ height: 48, borderRadius: 10 }} />)}
          </div>
        )}
        {loaded && projects.length === 0 && (
          <EmptyState icon="◫" title="No projects yet" hint="Add a project above to start configuring tasks for it." />
        )}
        {loaded && projects.length > 0 && (
          <div className="table-scroll"><table>
            <thead><tr><th>Name</th><th>Type</th><th>Priority</th><th>Status</th><th>Eligibility</th><th style={{ textAlign: 'right' }}>Actions</th></tr></thead>
            <tbody>
              {projects.map(p => (
                <tr key={p.id} style={{ opacity: p.status === 'archived' ? 0.55 : 1 }}>
                  <td style={{ fontWeight: 600 }}><Link to={`/projects/${p.id}`}>{p.name}</Link></td>
                  <td><span className="badge neutral"><span className="badge-dot" />{p.type}</span></td>
                  <td className="mono">{p.priority}</td>
                  <td><Badge status={p.status === 'active' ? 'active' : p.status === 'stopped' || p.status === 'archived' ? 'failed' : p.status}>{p.status}</Badge></td>
                  <td><EligibilityBadge project={p} /></td>
                  <td style={{ textAlign: 'right' }}>
                    <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
                      <Link to={`/projects/new?project=${p.id}`} style={{ fontSize: 12.5 }}>Draft criteria</Link>
                      {p.status === 'archived' ? (
                        <button className="sm" onClick={() => restore(p)}>Restore</button>
                      ) : (
                        <>
                          {p.status === 'stopped' && !isDeclared(p) && (
                            <button className="sm" onClick={() => resume(p)}>Resume</button>
                          )}
                          {p.status !== 'stopped' && !isDeclared(p) && (
                            <button className="sm" onClick={() => stop(p)}>Stop</button>
                          )}
                          {!isDeclared(p) && (
                            <button className="sm" onClick={() => setEligibilityTarget(p)}>Declare eligibility</button>
                          )}
                          {isDeclared(p) && (
                            <button className="sm" onClick={() => clearEligibility(p)}>Clear eligibility</button>
                          )}
                          <button className="sm danger" onClick={() => archive(p)}>Archive</button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </Card>

      {eligibilityTarget && (
        <EligibilityModal
          project={eligibilityTarget}
          onClose={() => setEligibilityTarget(null)}
          onSaved={() => { setEligibilityTarget(null); fetchProjects() }}
        />
      )}
    </div>
  )
}
