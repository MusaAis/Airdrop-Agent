import React, { useMemo, useState } from 'react'
import api from '../api'
import useApi, { apiError } from '../hooks/useApi'
import { useToast } from '../components/Toast'
import { useConfirm } from '../components/Confirm'
import WalletManage from '../components/WalletManage'
import { Card, Badge, PageHeader, StatTile, EmptyState, DataTable, Segmented, Field } from '../components/ui'
import { shortAddr } from '../lib/format'

const FILTERS = ['all', 'active', 'paused', 'cooldown', 'blacklisted', 'archived']

export default function Wallets() {
  const toast = useToast()
  const confirm = useConfirm()
  const { data, loading, reload } = useApi(() => api.get('/wallets/').then(r => r.data), [])
  const wallets = Array.isArray(data) ? data : []

  const [count, setCount] = useState(1)
  const [privKey, setPrivKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [managing, setManaging] = useState(null)
  const [filter, setFilter] = useState('all')
  const [q, setQ] = useState('')

  const run = async (fn, ok) => {
    setBusy(true)
    try { await fn(); if (ok) toast.success(ok); await reload() }
    catch (e) { toast.error(e?.response ? apiError(e) : (e?.message || 'Request failed.')) }
    finally { setBusy(false) }
  }

  const generate = () => {
    const n = Math.max(1, Math.min(50, Number(count) || 1))
    return run(
      () => api.post('/wallets/generate', { count: n, start_index: wallets.length }).catch(e => {
        const d = e?.response?.data?.detail
        throw d ? e : new Error('Could not generate wallets. Is the master seed set and unlocked? (Settings → System controls)')
      }),
      `Generated ${n} wallet(s).`,
    )
  }

  const rerollAll = async () => {
    if (await confirm({ title: 'Re-roll every persona?', message: 'Gives every non-archived, non-gas wallet a NEW random persona and overwrites their behaviour settings (hours, sleep, gas multiplier, daily range).', confirmLabel: 'Re-roll all' }))
      run(() => api.post('/ops/persona/reroll-all').then(r => { toast.success(r.data.message); return r }))
  }

  const importWallet = async () => {
    const key = privKey.trim().replace(/^0x/, '')
    if (!key) return toast.error('Paste a private key first.')
    const ok = await confirm({
      title: 'Send a raw private key?',
      message: 'The key is sent over the network to your server and stored encrypted. Only continue if you fully trust this server and connection — generating HD wallets is safer.',
      confirmLabel: 'Import key', tone: 'danger',
    })
    if (!ok) return
    await run(() => api.post('/wallets/import', { private_key: key, tags: [] }), 'Wallet imported.')
    setPrivKey('')
  }

  const setStatus = (id, status, ok) => run(() => api.put(`/wallets/${id}/status?status=${status}`), ok)

  const archive = async w => {
    if (await confirm({ title: `Archive wallet #${w.id}?`, message: 'It stops running tasks. You can activate it again later.', confirmLabel: 'Archive', tone: 'danger' }))
      setStatus(w.id, 'archived', 'Wallet archived.')
  }

  const copy = w => { navigator.clipboard?.writeText(w.address); toast.info('Address copied') }

  const counts = useMemo(() => {
    const c = { active: 0, paused: 0, gas: 0 }
    for (const w of wallets) { if (w.status === 'active') c.active++; if (w.status === 'paused') c.paused++; if (w.is_gas_wallet) c.gas++ }
    return c
  }, [wallets])

  const visible = useMemo(() => wallets.filter(w =>
    (filter === 'all' || w.status === filter) &&
    (!q || `${w.id} ${w.address} ${(w.tags || []).join(' ')}`.toLowerCase().includes(q.toLowerCase())),
  ), [wallets, filter, q])

  const columns = [
    { key: 'id', label: 'ID', render: w => <span className="mono muted">{w.id}</span> },
    {
      key: 'address', label: 'Address',
      render: w => (
        <span className="row" style={{ gap: 6, justifyContent: 'flex-end' }}>
          <button className="ghost sm mono" style={{ padding: '4px 8px', fontSize: 12.5 }} title={w.address} onClick={() => copy(w)}>{shortAddr(w.address)}</button>
          {w.is_gas_wallet && <Badge tone="warning">gas</Badge>}
        </span>
      ),
    },
    { key: 'tags', label: 'Tags', render: w => <span className="muted" style={{ fontSize: 12 }}>{(w.tags || []).join(', ') || '—'}</span> },
    {
      key: 'status', label: 'Status',
      render: w => (
        <span className="row" style={{ gap: 6, justifyContent: 'flex-end' }}>
          <Badge status={w.status}>{w.status}</Badge>
          {w.failure_count > 0 && <span className="faint" style={{ fontSize: 11 }}>{w.failure_count} fail</span>}
        </span>
      ),
    },
    { key: 'health', label: 'Health', num: true, render: w => <span className="mono">{w.health_score ?? '—'}</span> },
    {
      key: 'sybil', label: 'Sybil', num: true,
      render: w => <span className="mono" style={{ color: (w.sybil_risk_score ?? 0) > 60 ? 'var(--rose)' : (w.sybil_risk_score ?? 0) > 30 ? 'var(--amber)' : 'inherit' }}>{w.sybil_risk_score ?? 0}</span>,
    },
    {
      key: 'actions', label: 'Actions', actions: true,
      render: w => (
        <div className="row" style={{ gap: 6, justifyContent: 'flex-end' }}>
          {w.status !== 'active' && <button className="sm" disabled={busy} onClick={() => setStatus(w.id, 'active', 'Wallet activated.')}>Activate</button>}
          {w.status !== 'paused' && w.status !== 'archived' && <button className="sm" disabled={busy} onClick={() => setStatus(w.id, 'paused', 'Wallet paused.')}>Pause</button>}
          <button className="sm" onClick={() => setManaging(w.id)}>Manage</button>
          {w.status !== 'archived' && <button className="sm danger" disabled={busy} onClick={() => archive(w)}>Archive</button>}
        </div>
      ),
    },
  ]

  return (
    <div className="stack">
      <PageHeader title="Wallets" subtitle="Generate HD wallets from your seed, or import a single key. Tap an address to copy it." />

      <div className="grid-stats">
        <Card><StatTile label="Total" value={loading ? '…' : wallets.length} /></Card>
        <Card><StatTile label="Active" value={loading ? '…' : counts.active} tone="signal" /></Card>
        <Card><StatTile label="Paused" value={loading ? '…' : counts.paused} tone="amber" /></Card>
        <Card><StatTile label="Gas wallets" value={loading ? '…' : counts.gas} tone="violet" /></Card>
      </div>

      <div className="grid">
        <Card title="Generate HD wallets">
          <p className="hint" style={{ marginBottom: 14 }}>Derives new wallets from your configured seed phrase. Safe and recommended.</p>
          <div className="row">
            <input type="number" value={count} min={1} max={50} onChange={e => setCount(e.target.value)} aria-label="How many wallets" />
            <button className="primary" onClick={generate} disabled={busy}>Generate</button>
            <button className="ghost sm" onClick={rerollAll} disabled={busy} title="Fresh random behaviour settings for every wallet">Re-roll all personas</button>
          </div>
        </Card>

        <Card title="Import private key">
          <p className="hint" style={{ marginBottom: 14 }}>Only do this on a server you fully trust. The key is hidden while you type.</p>
          <div className="row" style={{ flexWrap: 'nowrap' }}>
            <input
              className="grow mono" type="password" autoComplete="off" autoCapitalize="off" spellCheck={false}
              placeholder="0x… private key" value={privKey} onChange={e => setPrivKey(e.target.value)}
            />
            <button onClick={importWallet} disabled={busy || !privKey.trim()}>Import</button>
          </div>
        </Card>
      </div>

      <Card title="All wallets" action={<Segmented value={filter} onChange={setFilter} options={FILTERS} />}>
        <input placeholder="Search id, address or tag…" value={q} onChange={e => setQ(e.target.value)} style={{ width: '100%', marginBottom: 14 }} />
        <DataTable
          columns={columns} rows={visible} loading={loading}
          empty={<EmptyState icon="◇" title={wallets.length ? 'No wallets match' : 'No wallets yet'} hint={wallets.length ? 'Change the search or status filter.' : 'Generate HD wallets or import a private key to get started.'} />}
        />
      </Card>

      {managing && (
        <WalletManage
          wallet={wallets.find(x => x.id === managing)}
          onChanged={reload}
          onClose={() => setManaging(null)}
        />
      )}
    </div>
  )
}
