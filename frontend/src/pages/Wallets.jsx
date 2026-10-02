import React, { useMemo, useState } from 'react'
import api from '../api'
import useApi, { apiError } from '../hooks/useApi'
import { useToast } from '../components/Toast'
import { useConfirm } from '../components/Confirm'
import WalletManage from '../components/WalletManage'
import { Card, Badge, PageHeader, StatTile, EmptyState, DataTable, Segmented, Field } from '../components/ui'
import { shortAddr } from '../lib/format'

const FILTERS = ['all', 'active', 'paused', 'cooldown', 'archived']

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

  const run = async (fn, ok) => {
    setBusy(true)
    try { await fn(); if (ok) toast.success(ok); await reload() }
    catch (e) { toast.error(apiError(e)) }
    finally { setBusy(false) }
  }

  const generate = () => {
    const n = Math.max(1, Math.min(100, Number(count) || 1))
    return run(() => api.post('/wallets/generate', { count: n, start_index: wallets.length }), `Generated ${n} wallet(s).`)
  }

  const importWallet = async () => {
    const key = privKey.trim()
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

  const visible = filter === 'all' ? wallets : wallets.filter(w => w.status === filter)

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
    { key: 'status', label: 'Status', render: w => <Badge status={w.status}>{w.status}</Badge> },
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
            <input type="number" value={count} min={1} max={100} onChange={e => setCount(e.target.value)} aria-label="How many wallets" />
            <button className="primary" onClick={generate} disabled={busy}>Generate</button>
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
        <DataTable
          columns={columns} rows={visible} loading={loading}
          empty={<EmptyState icon="◇" title={wallets.length ? 'No wallets in this view' : 'No wallets yet'} hint={wallets.length ? 'Try another filter.' : 'Generate HD wallets or import a private key to get started.'} />}
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
