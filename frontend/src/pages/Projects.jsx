import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../api'
import useApi, { apiError } from '../hooks/useApi'
import { useToast } from '../components/Toast'
import { useConfirm } from '../components/Confirm'
import { Card, Badge, PageHeader, EmptyState, DataTable, Modal, Field } from '../components/ui'

function EligibilityBadge({ project }) {
  if (project.eligibility_status === 'eligible') {
    const val = project.eligibility_value_usd
    return <Badge tone="success">Eligible{val ? ` · $${Number(val).toFixed(2)}` : ''}</Badge>
  }
  if (project.eligibility_status === 'not_eligible') return <Badge tone="danger">Not eligible</Badge>
  return <Badge tone="neutral">Pending</Badge>
}

function EligibilityModal({ project, onClose, onSaved }) {
  const [choice, setChoice] = useState('eligible')
  const [value, setValue] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const save = async () => {
    setError(''); setSaving(true)
    try {
      await api.post(`/projects/${project.id}/eligibility`, {
        eligible: choice === 'eligible',
        value_usd: choice === 'eligible' && value ? parseFloat(value) : null,
      })
      onSaved()
    } catch (e) {
      setError(apiError(e, 'Could not save eligibility.'))
    } finally { setSaving(false) }
  }

  return (
    <Modal title={`Declare eligibility — ${project.name}`} onClose={onClose}>
      <p className="hint" style={{ margin: '4px 0 16px' }}>
        This stops the agent from scheduling any further tasks for this project, whether it's eligible or not. You can clear it later if it was a mistake.
      </p>
      <div className="stack-sm">
        <label className="check" style={{ fontSize: 13.5, color: 'var(--text)' }}>
          <input type="radio" name="elig" checked={choice === 'eligible'} onChange={() => setChoice('eligible')} /> Eligible
        </label>
        {choice === 'eligible' && (
          <input placeholder="Estimated airdrop value in USD (optional)" type="number" inputMode="decimal" step="any" value={value} onChange={e => setValue(e.target.value)} style={{ width: '100%' }} />
        )}
        <label className="check" style={{ fontSize: 13.5, color: 'var(--text)' }}>
          <input type="radio" name="elig" checked={choice === 'not_eligible'} onChange={() => setChoice('not_eligible')} /> Not eligible
        </label>
      </div>
      {error && <div className="error" style={{ marginTop: 12 }}>{error}</div>}
      <div className="modal-actions">
        <button className="ghost" onClick={onClose} disabled={saving}>Cancel</button>
        <button className="primary" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Declare'}</button>
      </div>
    </Modal>
  )
}

// Types the quick-add form offers. The guided wizard (and the AI prompts) only know
// dapp / ecosystem, so quick-add offers the same set to keep the three paths consistent.
const QUICK_TYPES = [{ value: 'dapp', label: 'dApp' }, { value: 'ecosystem', label: 'Ecosystem' }]

export default function Projects() {
  const toast = useToast()
  const confirm = useConfirm()
  const [showArchived, setShowArchived] = useState(false)
  const [newProj, setNewProj] = useState({ name: '', type: 'dapp', chain_ids: '' })
  const [eligibilityTarget, setEligibilityTarget] = useState(null)

  const { data, loading, reload } = useApi(
    () => api.get('/projects/', { params: showArchived ? { include_archived: true } : {} }).then(r => r.data),
    [showArchived],
  )
  const projects = Array.isArray(data) ? data : []

  const run = async (fn, ok) => {
    try { const r = await fn(); toast.success(ok || r?.data?.message || 'Done.'); await reload() }
    catch (e) { toast.error(apiError(e)) }
  }

  const add = () => {
    if (!newProj.name.trim()) return
    return run(async () => {
      await api.post('/projects/', { ...newProj, chain_ids: newProj.chain_ids.split(',').map(s => Number(s.trim())).filter(n => Number.isInteger(n) && n > 0) })
      setNewProj({ name: '', type: 'dapp', chain_ids: '' })
    }, 'Project added.')
  }

  const archive = async p => {
    if (await confirm({ title: `Archive “${p.name}”?`, message: 'It stays in your records and history — this just stops it from farming and hides it from the default list.', confirmLabel: 'Archive', tone: 'danger' }))
      run(() => api.delete(`/projects/${p.id}`), 'Project archived.')
  }
  const stop = async p => {
    if (await confirm({ title: `Stop “${p.name}”?`, message: 'This halts farming but keeps it visible (unlike archive).', confirmLabel: 'Stop farming', tone: 'danger' }))
      run(() => api.post(`/projects/${p.id}/stop`), 'Project stopped.')
  }
  const resume = p => run(() => api.put(`/projects/${p.id}`, { status: 'active' }), 'Project resumed.')
  const restore = p => run(() => api.post(`/projects/${p.id}/restore`), 'Project restored.')
  const clearEligibility = async p => {
    if (await confirm({ title: `Clear eligibility for “${p.name}”?`, message: 'Farming can resume once cleared.', confirmLabel: 'Clear' }))
      run(() => api.post(`/projects/${p.id}/eligibility/clear`), 'Eligibility cleared.')
  }

  const isDeclared = p => p.eligibility_status === 'eligible' || p.eligibility_status === 'not_eligible'

  const columns = [
    { key: 'name', label: 'Name', render: p => <Link to={`/projects/${p.id}`} style={{ fontWeight: 600 }}>{p.name}</Link> },
    { key: 'type', label: 'Type', render: p => <Badge tone="neutral">{p.type}</Badge> },
    { key: 'priority', label: 'Priority', render: p => <span className="mono">{p.priority}</span> },
    { key: 'status', label: 'Status', render: p => <Badge status={p.status}>{p.status}</Badge> },
    { key: 'elig', label: 'Eligibility', render: p => <EligibilityBadge project={p} /> },
    {
      key: 'actions', label: 'Actions', actions: true,
      render: p => (
        <div className="row" style={{ gap: 6, justifyContent: 'flex-end' }}>
          <Link to={`/projects/new?project=${p.id}`} style={{ fontSize: 12.5 }}>Draft criteria</Link>
          {p.status === 'archived' ? (
            <button className="sm" onClick={() => restore(p)}>Restore</button>
          ) : (
            <>
              {p.status === 'stopped' && !isDeclared(p) && <button className="sm" onClick={() => resume(p)}>Resume</button>}
              {p.status !== 'stopped' && !isDeclared(p) && <button className="sm" onClick={() => stop(p)}>Stop</button>}
              {!isDeclared(p) && <button className="sm" onClick={() => setEligibilityTarget(p)}>Declare eligibility</button>}
              {isDeclared(p) && <button className="sm" onClick={() => clearEligibility(p)}>Clear eligibility</button>}
              <button className="sm danger" onClick={() => archive(p)}>Archive</button>
            </>
          )}
        </div>
      ),
    },
  ]

  return (
    <div className="stack">
      <PageHeader
        title="Projects"
        subtitle="Quick add takes a name, type and chains. Use guided setup for tasks and AI-drafted criteria."
        actions={<Link to="/projects/new"><button className="primary">Guided setup →</button></Link>}
      />

      <Card title="Quick add">
        <div className="row">
          <input className="grow" style={{ minWidth: 160 }} placeholder="Name" value={newProj.name} onChange={e => setNewProj({ ...newProj, name: e.target.value })} />
          <select value={newProj.type} onChange={e => setNewProj({ ...newProj, type: e.target.value })}>
            {QUICK_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
          <input className="grow" style={{ minWidth: 160 }} placeholder="Chain IDs (comma sep)" value={newProj.chain_ids} onChange={e => setNewProj({ ...newProj, chain_ids: e.target.value })} />
          <button className="primary" onClick={add} disabled={!newProj.name.trim()}>Add</button>
        </div>
      </Card>

      <Card
        title="All projects"
        action={<label className="check"><input type="checkbox" checked={showArchived} onChange={e => setShowArchived(e.target.checked)} /> Show archived</label>}
      >
        <DataTable
          columns={columns} rows={projects} loading={loading} skeletonRows={3}
          rowStyle={p => (p.status === 'archived' ? { opacity: 0.55 } : undefined)}
          empty={<EmptyState icon="◫" title="No projects yet" hint="Add a project above to start configuring tasks for it." />}
        />
      </Card>

      {eligibilityTarget && (
        <EligibilityModal
          project={eligibilityTarget}
          onClose={() => setEligibilityTarget(null)}
          onSaved={() => { setEligibilityTarget(null); toast.success('Eligibility declared.'); reload() }}
        />
      )}
    </div>
  )
}
