import React, { useEffect, useState, useCallback } from 'react'
import api from '../api'
import { Card, Badge, EmptyState } from '../components/ui'

const short = a => (a ? `${a.slice(0, 6)}…${a.slice(-4)}` : '')

export default function Proxies() {
  const [proxies, setProxies] = useState([])
  const [wallets, setWallets] = useState([])
  const [loaded, setLoaded] = useState(false)
  const [form, setForm] = useState({ url: '', type: 'http' })
  const [msg, setMsg] = useState('')
  const [tests, setTests] = useState({})

  const load = useCallback(async () => {
    try {
      const [p, w] = await Promise.all([api.get('/proxies/'), api.get('/wallets/')])
      setProxies(p.data); setWallets(w.data)
    } catch { setMsg('Could not load proxies.') } finally { setLoaded(true) }
  }, [])
  useEffect(() => { load() }, [load])

  const run = async (fn) => {
    setMsg('')
    try { await fn(); await load() } catch (e) { setMsg(e?.response?.data?.detail || 'Request failed.') }
  }

  const add = () => form.url.trim() && run(async () => {
    await api.post('/proxies/', form)
    setForm({ url: '', type: form.type })
  })
  const assign = (id, walletId) => run(() => api.put(`/proxies/${id}/assign`, { wallet_id: walletId ? Number(walletId) : null }))
  const toggle = (p) => run(() => api.put(`/proxies/${p.id}/active`, { active: !p.is_active }))
  const remove = (p) => window.confirm('Delete this proxy?') && run(() => api.delete(`/proxies/${p.id}`))
  const test = async (p) => {
    setTests(t => ({ ...t, [p.id]: 'testing…' }))
    try {
      const r = (await api.post(`/proxies/${p.id}/test`)).data
      setTests(t => ({ ...t, [p.id]: r.ok ? `ok · ${r.ip} · ${r.latency_ms}ms` : `failed: ${r.error}` }))
      load()
    } catch { setTests(t => ({ ...t, [p.id]: 'test request failed' })) }
  }

  const walletLabel = id => { const w = wallets.find(x => x.id === id); return w ? `#${w.id} ${short(w.address)}` : `#${id}` }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <Card title="Add proxy">
        <p style={{ fontSize: 12.5, color: 'var(--text-dim)', marginTop: -8, marginBottom: 14 }}>
          One proxy per wallet. Faucet claims for a wallet with an active proxy go through it, and fail rather than fall back to the server's own IP.
          Passwords are never shown again after saving.
        </p>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <input className="mono" placeholder="http://user:pass@host:port" value={form.url}
            onChange={e => setForm({ ...form, url: e.target.value })} style={{ flex: 1, minWidth: 260 }} />
          <input placeholder="type" value={form.type} onChange={e => setForm({ ...form, type: e.target.value })} style={{ width: 120 }} />
          <button className="primary" onClick={add}>Add</button>
        </div>
      </Card>

      {msg && <div className="error">{msg}</div>}

      <Card title="Proxies">
        {!loaded ? <div className="skeleton" style={{ height: 60, borderRadius: 10 }} />
          : proxies.length === 0 ? <EmptyState icon="⇄" title="No proxies yet" hint="Add one above, then assign it to a wallet." />
          : (
            <div className="table-scroll"><table>
              <thead><tr><th>Proxy</th><th>Status</th><th>Wallet</th><th>Test</th><th></th></tr></thead>
              <tbody>
                {proxies.map(p => (
                  <tr key={p.id}>
                    <td><div className="mono" style={{ fontSize: 12.5 }}>{p.url}</div><div style={{ fontSize: 11, color: 'var(--text-faint)' }}>{p.type}</div></td>
                    <td><button className="ghost sm" onClick={() => toggle(p)}><Badge status={p.is_active ? 'active' : 'paused'}>{p.is_active ? 'active' : 'off'}</Badge></button></td>
                    <td>
                      <select value={p.wallet_id ?? ''} onChange={e => assign(p.id, e.target.value)} style={{ maxWidth: 190 }}>
                        <option value="">— unassigned —</option>
                        {wallets.map(w => <option key={w.id} value={w.id}>#{w.id} {short(w.address)}</option>)}
                      </select>
                      {p.wallet_id && <div style={{ fontSize: 11, color: 'var(--text-faint)' }}>{walletLabel(p.wallet_id)}</div>}
                    </td>
                    <td style={{ fontSize: 12 }}>
                      <button className="ghost sm" onClick={() => test(p)}>Test</button>
                      <div className="mono" style={{ fontSize: 11, color: 'var(--text-dim)' }}>{tests[p.id] || (p.last_verified ? `verified ${new Date(p.last_verified + 'Z').toLocaleDateString()}` : '')}</div>
                    </td>
                    <td><button className="sm danger" onClick={() => remove(p)}>Delete</button></td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          )}
      </Card>
    </div>
  )
}
