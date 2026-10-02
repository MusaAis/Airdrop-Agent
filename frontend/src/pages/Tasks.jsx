import React, { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import api from '../api'
import { useConfirm } from '../components/Confirm'
import { Card, Badge, EmptyState, DataTable, PageHeader, Field } from '../components/ui'

const err = e => e?.response?.data?.detail || 'Request failed.'
const n = v => (v === '' || v == null ? undefined : Number(v))
const isAddr = v => /^0x[a-fA-F0-9]{40}$/.test(v || '')

// Parameter keys each task class reads (see backend/tasks/*.py). Required ones must be
// filled in before the task can be enabled; it is created disabled otherwise.
const PARAM_TEMPLATES = {
  swap: { router_address: '' },
  bridge: { bridge_contract: '', dest_chain_id: '', bridge_type: 'erc20' },
  transfer: { to_address: '' },
  stake: { staking_contract: '' },
  unstake: { staking_contract: '' },
  provide_liquidity: { router_address: '' },
  remove_liquidity: { router_address: '', lp_token_address: '' },
  interact_contract: { contract_address: '', data: '0x' },
}
const REQUIRED = {
  swap: ['router_address'], bridge: ['bridge_contract', 'dest_chain_id'], transfer: [],
  stake: ['staking_contract'], unstake: ['staking_contract'], provide_liquidity: ['router_address'],
  remove_liquidity: ['router_address', 'lp_token_address'], interact_contract: ['contract_address'],
}
const EMPTY_NEW = { task_type: 'swap', chain_id: '', min_amount: '', max_amount: '', token_in: '', token_out: '', daily_tx_min: 2, daily_tx_max: 7, frequency_mins: 120, parameters: JSON.stringify(PARAM_TEMPLATES.swap, null, 2) }

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
    <Field label={label}><input value={f[k]} inputMode={props.type === 'number' ? 'decimal' : undefined} onChange={e => set({ [k]: e.target.value })} {...props} /></Field>
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
    <div className="stack-sm" style={{ padding: 8 }}>
      <div className="grid-fields">
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
        <Field label="Distribution">
          <select value={f.amount_distribution} onChange={e => set({ amount_distribution: e.target.value })}>
            <option value="weighted_low">weighted low</option><option value="weighted_high">weighted high</option><option value="uniform">uniform</option>
          </select>
        </Field>
      </div>
      <div className="row" style={{ gap: 18 }}>
        <label className="check"><input type="checkbox" checked={f.amount_vary_daily} onChange={e => set({ amount_vary_daily: e.target.checked })} /> vary amounts daily</label>
        <label className="check"><input type="checkbox" checked={f.bidirectional} onChange={e => set({ bidirectional: e.target.checked })} /> bidirectional</label>
      </div>
      <textarea className="mono" style={{ width: '100%' }} rows={5} value={f.parameters} onChange={e => set({ parameters: e.target.value })} placeholder="parameters JSON (contract addresses etc.)" />
      <div className="row">
        <button className="primary sm" onClick={save}>Save</button>
        <select value={runWallet} onChange={e => setRunWallet(e.target.value)} style={{ maxWidth: 200 }}>
          <option value="">random active wallet</option>
          {wallets.filter(w => w.status === 'active' && !w.is_gas_wallet).map(w => <option key={w.id} value={w.id}>#{w.id} {w.address.slice(0, 8)}…</option>)}
        </select>
        <button className="sm" onClick={run}>Run now</button>
      </div>
      {msg && <div className="hint">{msg}</div>}
    </div>
  )
}

function AddTask({ projectId, chains, onCreated }) {
  const [f, setF] = useState(EMPTY_NEW)
  const [msg, setMsg] = useState('')
  const set = p => setF(x => ({ ...x, ...p }))

  const create = async () => {
    setMsg('')
    if (!f.chain_id) return setMsg('Choose a chain.')
    const min = parseFloat(f.min_amount), max = parseFloat(f.max_amount)
    if (!(min > 0) || !(max >= min)) return setMsg('Enter a valid min/max amount (max ≥ min, both > 0).')
    let params
    try { params = JSON.parse(f.parameters || '{}') } catch { return setMsg('Parameters must be valid JSON.') }
    const clean = {}
    for (const [k, v] of Object.entries(params)) { if (v !== '' && v != null) clean[k] = v }
    if (clean.dest_chain_id != null) {
      const d = Number(clean.dest_chain_id)
      if (!Number.isFinite(d)) return setMsg('dest_chain_id must be a number.')
      clean.dest_chain_id = d
    }
    for (const [k, v] of Object.entries(clean)) {
      if ((k.endsWith('_address') || k.endsWith('_contract')) && !isAddr(v)) return setMsg(`${k} is not a valid 0x address.`)
    }
    const missing = (REQUIRED[f.task_type] || []).filter(k => clean[k] == null)
    try {
      await api.post(`/projects/${projectId}/tasks`, {
        project_id: Number(projectId), task_type: f.task_type, chain_id: Number(f.chain_id), parameters: clean,
        min_amount: min, max_amount: max, frequency_mins: Number(f.frequency_mins) || 120,
        daily_tx_min: Number(f.daily_tx_min) || 2, daily_tx_max: Number(f.daily_tx_max) || 7,
        token_in: f.token_in.trim() || null, token_out: f.token_out.trim() || null,
        enabled: missing.length === 0,
      })
      setF(EMPTY_NEW)
      onCreated(missing.length ? `Task created DISABLED - still needs: ${missing.join(', ')}. Edit it, then enable.` : 'Task created and enabled.')
    } catch (e) { setMsg(err(e)) }
  }

  return (
    <Card title="Add task">
      <div className="grid-fields">
        <Field label="Type">
          <select value={f.task_type} onChange={e => set({ task_type: e.target.value, parameters: JSON.stringify(PARAM_TEMPLATES[e.target.value], null, 2) })}>
            {Object.keys(PARAM_TEMPLATES).map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </Field>
        <Field label="Chain">
          <select value={f.chain_id} onChange={e => set({ chain_id: e.target.value })}>
            <option value="">Select…</option>{chains.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </Field>
        <Field label="Min amount"><input type="number" inputMode="decimal" step="any" value={f.min_amount} onChange={e => set({ min_amount: e.target.value })} /></Field>
        <Field label="Max amount"><input type="number" inputMode="decimal" step="any" value={f.max_amount} onChange={e => set({ max_amount: e.target.value })} /></Field>
        <Field label="Token in"><input value={f.token_in} onChange={e => set({ token_in: e.target.value })} placeholder="symbol, e.g. ETH" /></Field>
        <Field label="Token out"><input value={f.token_out} onChange={e => set({ token_out: e.target.value })} placeholder="symbol" /></Field>
        <Field label="Daily tx min"><input type="number" value={f.daily_tx_min} onChange={e => set({ daily_tx_min: e.target.value })} /></Field>
        <Field label="Daily tx max"><input type="number" value={f.daily_tx_max} onChange={e => set({ daily_tx_max: e.target.value })} /></Field>
        <Field label="Frequency (min)"><input type="number" value={f.frequency_mins} onChange={e => set({ frequency_mins: e.target.value })} /></Field>
      </div>
      <textarea className="mono" rows={4} style={{ width: '100%', marginTop: 10 }} value={f.parameters} onChange={e => set({ parameters: e.target.value })} spellCheck={false} autoCapitalize="off" />
      <p className="hint faint" style={{ margin: '6px 0 10px' }}>
        Fill in the addresses above. Empty values are dropped; a task missing a required one is saved disabled.
        Tokens must exist in the chain's token registry (Chains → Manage).
      </p>
      <button className="primary sm" onClick={create}>Create task</button>
      {msg && <div className="error" style={{ marginTop: 10 }}>{msg}</div>}
    </Card>
  )
}

export default function Tasks() {
  const confirm = useConfirm()
  const [sp] = useSearchParams()
  const [projects, setProjects] = useState([])
  const [wallets, setWallets] = useState([])
  const [chains, setChains] = useState([])
  const [selectedProj, setSelectedProj] = useState('')
  const [tasks, setTasks] = useState([])
  const [loadingTasks, setLoadingTasks] = useState(false)
  const [open, setOpen] = useState(null)
  const [msg, setMsg] = useState('')

  const loadTasks = async (projId, keepOpen = false) => {
    if (!projId) { setSelectedProj(''); setTasks([]); return }
    setSelectedProj(String(projId)); setLoadingTasks(true)
    if (!keepOpen) setOpen(null)
    try { setTasks((await api.get(`/projects/${projId}/tasks`)).data) } catch (e) { setMsg(err(e)) } finally { setLoadingTasks(false) }
  }

  useEffect(() => {
    api.get('/projects/').then(r => setProjects(r.data)).catch(() => {})
    api.get('/wallets/').then(r => setWallets(r.data)).catch(() => {})
    api.get('/chains/').then(r => setChains(r.data)).catch(() => {})
    if (sp.get('project')) loadTasks(sp.get('project'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const toggle = async (t) => {
    setMsg('')
    try { await api.put(`/ops/tasks/${t.id}`, { enabled: !t.enabled }); loadTasks(selectedProj, true) } catch (e) { setMsg(err(e)) }
  }
  const runAll = async () => {
    if (!(await confirm({ title: 'Run all enabled tasks once?', message: 'Queues one run of every ENABLED task of this project, each on a different wallet.', confirmLabel: 'Queue them' }))) return
    setMsg('')
    try { setMsg((await api.post(`/ops/projects/${selectedProj}/trigger-all`)).data.message) } catch (e) { setMsg(err(e)) }
  }
  const chainName = id => chains.find(c => c.id === id)?.name || `#${id}`
  const selectedName = projects.find(p => String(p.id) === String(selectedProj))?.name

  const columns = [
    { key: 'id', label: 'ID', render: t => <span className="mono muted">{t.id}</span> },
    { key: 'type', label: 'Type', render: t => t.task_type },
    { key: 'chain', label: 'Chain', render: t => chainName(t.chain_id) },
    { key: 'amt', label: 'Min / Max', render: t => <span className="mono">{t.min_amount} – {t.max_amount}</span> },
    { key: 'daily', label: 'Daily tx', render: t => <span className="mono">{t.daily_tx_min}–{t.daily_tx_max}</span> },
    { key: 'deps', label: 'Deps', render: t => <span className="mono">{(t.dependency_task_ids || []).join(', ') || '—'}</span> },
    { key: 'enabled', label: 'Enabled', render: t => <button className="ghost sm" onClick={() => toggle(t)}><Badge status={t.enabled}>{t.enabled ? 'Enabled' : 'Disabled'}</Badge></button> },
    { key: 'edit', label: '', actions: true, render: t => <button className="sm" onClick={() => setOpen(open === t.id ? null : t.id)}>{open === t.id ? 'Close' : 'Edit'}</button> },
  ]

  return (
    <div className="stack">
      <PageHeader title="Tasks" subtitle="Choose a project to edit its tasks or add new ones. Disable a task instead of deleting it: transaction history is linked to it." />

      <Card>
        <select onChange={e => loadTasks(e.target.value)} value={selectedProj} style={{ minWidth: 240, width: '100%', maxWidth: 420 }}>
          <option value="">Select a project…</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </Card>

      {selectedProj && (
        <>
          <Card title={`Tasks · ${selectedName || `Project ${selectedProj}`}`} action={<button className="sm" onClick={runAll}>Run all enabled once</button>}>
            {msg && <div className="notice" style={{ marginBottom: 10 }}>{msg}</div>}
            <DataTable
              columns={columns} rows={tasks} loading={loadingTasks} skeletonRows={3}
              expanded={open}
              renderExpanded={t => <TaskEditor t={t} wallets={wallets} onSaved={() => loadTasks(selectedProj, true)} />}
              empty={<EmptyState icon="☐" title="No tasks configured" hint="Add one below." />}
            />
          </Card>
          <AddTask projectId={selectedProj} chains={chains} onCreated={m => { setMsg(m); loadTasks(selectedProj, true) }} />
        </>
      )}
    </div>
  )
}
