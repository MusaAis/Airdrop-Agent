import React, { useState } from 'react'
import api from '../api'
import useApi, { apiError } from '../hooks/useApi'
import { useToast } from '../components/Toast'
import { useConfirm } from '../components/Confirm'
import { Card, Badge, PageHeader, EmptyState, DataTable } from '../components/ui'
import { shortAddr, parseUtc } from '../lib/format'

export default function Proxies() {
  const toast = useToast()
  const confirm = useConfirm()
  const { data, loading, reload } = useApi(async () => {
    const [p, w] = await Promise.all([api.get('/proxies/'), api.get('/wallets/')])
    return { proxies: p.data, wallets: w.data }
  }, [])
  const proxies = data?.proxies || []
  const wallets = data?.wallets || []

  const [form, setForm] = useState({ url: '', type: 'http' })
  const [tests, setTests] = useState({})

  const run = async (fn, ok) => {
    try { await fn(); if (ok) toast.success(ok); await reload() } catch (e) { toast.error(apiError(e)) }
  }

  const add = () => form.url.trim() && run(async () => {
    await api.post('/proxies/', form)
    setForm({ url: '', type: form.type })
  }, 'Proxy added.')
  const assign = (id, walletId) => run(() => api.put(`/proxies/${id}/assign`, { wallet_id: walletId ? Number(walletId) : null }))
  const toggle = p => run(() => api.put(`/proxies/${p.id}/active`, { active: !p.is_active }))
  const remove = async p => {
    if (await confirm({ title: 'Delete this proxy?', message: 'Any wallet using it will go back to claiming from the server IP — or fail, if it requires a proxy.', confirmLabel: 'Delete', tone: 'danger' }))
      run(() => api.delete(`/proxies/${p.id}`), 'Proxy deleted.')
  }
  const test = async p => {
    setTests(t => ({ ...t, [p.id]: 'testing…' }))
    try {
      const r = (await api.post(`/proxies/${p.id}/test`)).data
      setTests(t => ({ ...t, [p.id]: r.ok ? `ok · ${r.ip} · ${r.latency_ms}ms` : `failed: ${r.error}` }))
      reload()
    } catch { setTests(t => ({ ...t, [p.id]: 'test request failed' })) }
  }

  const verified = p => {
    const d = parseUtc(p.last_verified)
    return d ? `verified ${d.toLocaleDateString()}` : ''
  }

  const columns = [
    {
      key: 'url', label: 'Proxy',
      render: p => (<div style={{ minWidth: 0 }}><div className="mono" style={{ fontSize: 12.5, overflowWrap: 'anywhere' }}>{p.url}</div><div className="faint" style={{ fontSize: 11 }}>{p.type}</div></div>),
    },
    { key: 'status', label: 'Status', render: p => <button className="ghost sm" onClick={() => toggle(p)}><Badge status={p.is_active ? 'active' : 'paused'}>{p.is_active ? 'active' : 'off'}</Badge></button> },
    {
      key: 'wallet', label: 'Wallet',
      render: p => (
        <select value={p.wallet_id ?? ''} onChange={e => assign(p.id, e.target.value)} style={{ maxWidth: 200 }}>
          <option value="">— unassigned —</option>
          {wallets.map(w => <option key={w.id} value={w.id}>#{w.id} {shortAddr(w.address)}</option>)}
        </select>
      ),
    },
    {
      key: 'test', label: 'Test',
      render: p => (<div style={{ textAlign: 'right' }}><button className="ghost sm" onClick={() => test(p)}>Test</button><div className="mono faint" style={{ fontSize: 11 }}>{tests[p.id] || verified(p)}</div></div>),
    },
    { key: 'del', label: '', actions: true, render: p => <button className="sm danger" onClick={() => remove(p)}>Delete</button> },
  ]

  return (
    <div className="stack">
      <PageHeader title="Proxies" subtitle="One proxy per wallet. Faucet claims for a wallet with an active proxy go through it, and fail rather than fall back to the server's own IP. Passwords are never shown again after saving." />

      <Card title="Add proxy">
        <div className="row">
          <input className="mono grow" style={{ minWidth: 240 }} placeholder="http://user:pass@host:port" value={form.url} onChange={e => setForm({ ...form, url: e.target.value })} autoCapitalize="off" spellCheck={false} />
          <select value={form.type} onChange={e => setForm({ ...form, type: e.target.value })}>
            <option value="http">http</option><option value="https">https</option><option value="socks5">socks5</option><option value="socks5h">socks5h</option>
          </select>
          <button className="primary" onClick={add} disabled={!form.url.trim()}>Add</button>
        </div>
      </Card>

      <Card title="Proxies">
        <DataTable
          columns={columns} rows={proxies} loading={loading} skeletonRows={2}
          empty={<EmptyState icon="⇄" title="No proxies yet" hint="Add one above, then assign it to a wallet." />}
        />
      </Card>
    </div>
  )
}
