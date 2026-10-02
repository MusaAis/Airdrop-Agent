import React, { useEffect, useState } from 'react'
import api from '../api'
import { Card, Badge, EmptyState, DataTable, PageHeader } from '../components/ui'

const err = e => e?.response?.data?.detail || 'Request failed.'
const n = v => (v === '' || v == null ? undefined : Number(v))

function toForm(t) {
  return {
    min_amount: t.min_amount ?? '', max_amount: t.max_amount ?? '', amount_distribution: t.amount_distribution || 'weighted_low',
    amount_vary_daily: !!t.amount_vary_daily, daily_tx_min: t.daily_tx_min ?? '', daily_tx_max: t.daily_tx_max ?? '',
    frequency_mins: t.frequency_mins ?? '', slippage_tolerance: t.slippage_tolerance ?? '', deadline_mins: t.deadline_mins ?? '',
    token_in: t.token_in || '', token_out: t.token_out || '', bidirectional: !!t.bidirectional,
    token_in_reverse: t.token_in_reverse || '', token_out_reverse: t.token_out_reverse || '',
    dependency_task_ids: (t.dependency_task_ids || []).join(', '),
    parameters: JSON.stringify(t.parameters || {}, null, 2),
  }
}

function TaskEditor({ t, wallets, onSaved }) {
  const [f, setF] = useState(toForm(t))
  const [msg, setMsg] = useState('')
  const [runWallet, setRunWallet] = useState('')
  const set = p => setF(x => ({ ...x, ...p }))
  const field = (k, label, props = {}) => (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: 'var(--text-dim)' }}>
      {label}<input value={f[k]} onChange={e => set({ [k]: e.target.value })} style={{ width: '100%' }} {...props} />
    </label>
  )

  const save = async () => {
    setMsg('')
    let parameters
    try { parameters = JSON.parse(f.parameters || '{}') } catch { return setMsg('Parameters must be valid JSON.') }
    const deps = f.dependency_task_ids.split(',').map(s => s.trim()).filter(Boolean).map(Number)
    if (deps.some(Number.isNaN)) return setMsg('Dependencies must be task ids separated by commas.')
    try {
      await api.put(`/ops/tasks/${t.id}`, {
        min_amount: n(f.min_amount), max_amount: n(f.max_amount), amount_distribution: f.amount_distribution,
        amount_vary_daily: f.amount_vary_daily, daily_tx_min: n(f.daily_tx_min), daily_tx_max: n(f.daily_tx_max),
        frequency_mins: n(f.frequency_mins), slippage_tolerance: n(f.slippage_tolerance), deadline_mins: n(f.deadline_mins),
        token_in: f.token_in, token_out: f.token_out, bidirectional: f.bidirectional,
        token_in_reverse: f.token_in_reverse, token_out_reverse: f.token_out_reverse,
        dependency_task_ids: deps, parameters,
      })
      setMsg('Saved.'); onSaved()
    } catch (e) { setMsg(err(e)) }
  }
  const run = async () => {
    setMsg('')
    try { setMsg((await api.post(`/ops/tasks/${t.id}/trigger`, { wallet_id: runWallet ? Number(runWallet) : null })).data.message) } catch (e) { setMsg(err(e)) }
  }

  return (
    <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(170px, 1fr))', gap: 10 }}>
        {field('min_amount', 'Min amount', { type: 'number', step: 'any' })}
        {field('max_amount', 'Max amount', { type: 'number', step: 'any' })}
        {field('daily_tx_min', 'Daily tx min', { type: 'number' })}
        {field('daily_tx_max', 'Daily tx max', { type: 'number' })}
        {field('frequency_mins', 'Frequency (min)', { type: 'number' })}
        {field('slippage_tolerance', 'Slippage (0.005 = 0.5%)', { type: 'number', step: 'any' })}
        {field('deadline_mins', 'Deadline (min)', { type: 'number' })}
        {field('token_in', 'Token in')}
        {field('token_out', 'Token out')}
        {f.bidirectional && field('token_in_reverse', 'Reverse token in')}
        {f.bidirectional && field('token_out_reverse', 'Reverse token out')}
        {field('dependency_task_ids', 'Depends on task ids')}
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: 'var(--text-dim)' }}>
          Distribution
          <select value={f.amount_distribution} onChange={e => set({ amount_distribution: e.target.value })}>
            <option value="weighted_low">weighted low</option><option value="weighted_high">weighted high</option><option value="uniform">uniform</option>
          </select>
        </label>
      </div>
      <div style={{ display: 'flex', gap: 16, fontSize: 13 }}>
        <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}><input type="checkbox" style={{ width: 'auto' }} checked={f.amount_vary_daily} onChange={e => set({ amount_vary_daily: e.target.checked })} /> vary amounts daily</label>
        <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}><input type="checkbox" style={{ width: 'auto' }} checked={f.bidirectional} onChange={e => set({ bidirectional: e.target.checked })} /> bidirectional</label>
      </div>
      <textarea className="mono" rows={5} value={f.parameters} onChange={e => set({ parameters: e.target.value })} placeholder="parameters JSON (contract addresses etc.)" />
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <button className="primary sm" onClick={save}>Save</button>
        <select value={runWallet} onChange={e => setRunWallet(e.target.value)} style={{ maxWidth: 200 }}>
          <option value="">random active wallet</option>
          {wallets.filter(w => w.status === 'active' && !w.is_gas_wallet).map(w => <option key={w.id} value={w.id}>#{w.id} {w.address.slice(0, 8)}…</option>)}
        </select>
        <button className="sm" onClick={run}>Run now</button>
      </div>
      {msg && <div style={{ fontSize: 13, color: 'var(--text-dim)' }}>{msg}</div>}
    </div>
  )
}

export default function Tasks() {
  const [projects, setProjects] = useState([])
  const [wallets, setWallets] = useState([])
  const [selectedProj, setSelectedProj] = useState('')
  const [tasks, setTasks] = useState([])
  const [loadingTasks, setLoadingTasks] = useState(false)
  const [open, setOpen] = useState(null)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    api.get('/projects/').then(r => setProjects(r.data)).catch(() => {})
    api.get('/wallets/').then(r => setWallets(r.data)).catch(() => {})
  }, [])

  const loadTasks = async (projId) => {
    setSelectedProj(projId)
    if (!projId) { setTasks([]); return }
    setLoadingTasks(true); setOpen(null); setMsg('')
    try { setTasks((await api.get(`/projects/${projId}/tasks`)).data) }
    catch (e) { setMsg(err(e)) }
    finally { setLoadingTasks(false) }
  }
  const toggle = async (t) => {
    setMsg('')
    try { await api.put(`/ops/tasks/${t.id}`, { enabled: !t.enabled }); loadTasks(selectedProj) } catch (e) { setMsg(err(e)) }
  }
  const selectedName = projects.find(p => String(p.id) === String(selectedProj))?.name

  const columns = [
    { key: 'id', label: 'ID', render: t => <span className="mono muted">{t.id}</span> },
    { key: 'type', label: 'Type', render: t => t.task_type },
    { key: 'amt', label: 'Min / Max', render: t => <span className="mono">{t.min_amount} – {t.max_amount}</span> },
    { key: 'daily', label: 'Daily tx', render: t => <span className="mono">{t.daily_tx_min}–{t.daily_tx_max}</span> },
    { key: 'deps', label: 'Deps', render: t => <span className="mono">{(t.dependency_task_ids || []).join(', ') || '—'}</span> },
    { key: 'enabled', label: 'Enabled', render: t => <button className="ghost sm" onClick={() => toggle(t)}><Badge status={t.enabled}>{t.enabled ? 'Enabled' : 'Disabled'}</Badge></button> },
    { key: 'edit', label: '', actions: true, render: t => <button className="sm" onClick={() => setOpen(open === t.id ? null : t.id)}>{open === t.id ? 'Close' : 'Edit'}</button> },
  ]

  return (
    <div className="stack">
      <PageHeader title="Tasks" subtitle="Choose a project, then edit its task configurations. New tasks are created from Projects → Guided setup." />

      <Card>
        <select value={selectedProj} onChange={e => loadTasks(e.target.value)} style={{ minWidth: 240, width: '100%', maxWidth: 420 }}>
          <option value="">Select a project…</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </Card>

      {selectedProj && (
        <Card title={`Tasks · ${selectedName || `Project ${selectedProj}`}`}>
          {msg && <div className="error" style={{ marginBottom: 10 }}>{msg}</div>}
          <DataTable
            columns={columns} rows={tasks} loading={loadingTasks} skeletonRows={3}
            expanded={open}
            renderExpanded={t => <TaskEditor t={t} wallets={wallets} onSaved={() => loadTasks(selectedProj)} />}
            empty={<EmptyState icon="☐" title="No tasks configured" hint="This project has no task configurations yet." />}
          />
        </Card>
      )}
    </div>
  )
}
