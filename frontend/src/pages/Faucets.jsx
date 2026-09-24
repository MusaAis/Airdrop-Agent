import React, { useEffect, useState } from 'react'
import api from '../api'
import Spinner from '../components/Spinner'
import { Card, Badge, EmptyState, SkeletonRows } from '../components/ui'

const EMPTY_FORM = {
  id: null,
  chain_id: '',
  project_id: '',
  name: '',
  url: '',
  fallback_urls: '',
  method: 'POST',
  body_template: '{"address": "{address}"}',
  cooldown_hours: 24,
  enabled: true,
}

const EMPTY_TOKEN_FORM = { token_symbol: '', token_contract: '', amount_given: '', decimals: 18 }

export default function Faucets({ token }) {
  const [faucets, setFaucets] = useState([])
  const [chains, setChains] = useState([])
  const [wallets, setWallets] = useState([])
  const [loading, setLoading] = useState(false)
  const [initialLoad, setInitialLoad] = useState(true)
  const [actionMessage, setActionMessage] = useState('')

  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [tokenForms, setTokenForms] = useState({})
  const [expanded, setExpanded] = useState(null)

  const [claimWalletId, setClaimWalletId] = useState('')
  const [claiming, setClaiming] = useState(false)
  const [claimResult, setClaimResult] = useState(null)

  const fetchAll = async () => {
    setLoading(true)
    try {
      const [fRes, cRes, wRes] = await Promise.all([
        api.get('/faucets/'),
        api.get('/chains/'),
        api.get('/wallets/'),
      ])
      setFaucets(fRes.data)
      setChains(cRes.data)
      setWallets(wRes.data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
      setInitialLoad(false)
    }
  }

  useEffect(() => { fetchAll() }, [])

  const chainName = (id) => chains.find(c => c.id === id)?.name || (id ? `Chain #${id}` : '— (any)')

  const openCreate = () => { setForm(EMPTY_FORM); setShowForm(true) }
  const openEdit = (f) => {
    setForm({
      id: f.id,
      chain_id: f.chain_id ?? '',
      project_id: f.project_id ?? '',
      name: f.name,
      url: f.url,
      fallback_urls: (f.fallback_urls || []).join('\n'),
      method: f.method || 'POST',
      body_template: JSON.stringify(f.body_template || { address: '{address}' }),
      cooldown_hours: f.cooldown_hours,
      enabled: f.enabled,
    })
    setShowForm(true)
  }

  const saveFaucet = async () => {
    setActionMessage('')
    let body_template
    try {
      body_template = JSON.parse(form.body_template)
    } catch {
      setActionMessage('Body template must be valid JSON, e.g. {"address": "{address}"}')
      return
    }
    const payload = {
      chain_id: form.chain_id ? Number(form.chain_id) : null,
      project_id: form.project_id ? Number(form.project_id) : null,
      name: form.name,
      url: form.url,
      fallback_urls: form.fallback_urls.split('\n').map(s => s.trim()).filter(Boolean),
      method: form.method,
      body_template,
      cooldown_hours: Number(form.cooldown_hours),
      enabled: form.enabled,
    }
    setLoading(true)
    try {
      if (form.id) {
        await api.put(`/faucets/${form.id}`, payload)
      } else {
        await api.post('/faucets/', payload)
      }
      setShowForm(false)
      await fetchAll()
    } catch (e) {
      setActionMessage(e?.response?.data?.detail || 'Error saving faucet')
    } finally {
      setLoading(false)
    }
  }

  const toggleEnabled = async (f) => {
    setLoading(true)
    try {
      await api.put(`/faucets/${f.id}`, { enabled: !f.enabled })
      await fetchAll()
    } catch (e) {
      setActionMessage('Error toggling faucet')
    } finally {
      setLoading(false)
    }
  }

  const deleteFaucet = async (f) => {
    if (!window.confirm(`Delete faucet "${f.name}"? This cannot be undone.`)) return
    setLoading(true)
    try {
      await api.delete(`/faucets/${f.id}`)
      await fetchAll()
    } catch (e) {
      setActionMessage('Error deleting faucet')
    } finally {
      setLoading(false)
    }
  }

  const addToken = async (faucetId) => {
    const draft = tokenForms[faucetId] || EMPTY_TOKEN_FORM
    if (!draft.token_symbol || !draft.amount_given) {
      setActionMessage('Token symbol and amount are required')
      return
    }
    setLoading(true)
    try {
      await api.post('/faucets/tokens', {
        faucet_id: faucetId,
        token_symbol: draft.token_symbol,
        token_contract: draft.token_contract || null,
        amount_given: Number(draft.amount_given),
        decimals: Number(draft.decimals || 18),
      })
      setTokenForms(prev => ({ ...prev, [faucetId]: EMPTY_TOKEN_FORM }))
      await fetchAll()
    } catch (e) {
      setActionMessage('Error adding token')
    } finally {
      setLoading(false)
    }
  }

  const removeToken = async (tokenId) => {
    setLoading(true)
    try {
      await api.delete(`/faucets/tokens/${tokenId}`)
      await fetchAll()
    } catch (e) {
      setActionMessage('Error removing token')
    } finally {
      setLoading(false)
    }
  }

  const claimForWallet = async () => {
    if (!claimWalletId) return
    setClaiming(true)
    setClaimResult(null)
    try {
      const r = await api.post(`/faucets/request-all/${claimWalletId}`)
      setClaimResult(r.data)
    } catch (e) {
      setActionMessage('Error claiming faucets for this wallet')
    } finally {
      setClaiming(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <Card title="Claim Faucet for a Wallet">
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <select value={claimWalletId} onChange={e => setClaimWalletId(e.target.value)} style={{ minWidth: 220 }}>
            <option value="">Select a wallet…</option>
            {wallets.map(w => (
              <option key={w.id} value={w.id}>{w.address.slice(0, 8)}…{w.address.slice(-6)} ({w.status})</option>
            ))}
          </select>
          <button className="primary" onClick={claimForWallet} disabled={!claimWalletId || claiming}>
            {claiming ? <Spinner inline size={14} /> : 'Claim All Tokens (all chains)'}
          </button>
        </div>
        {claimResult && (
          <div style={{ marginTop: 14, fontSize: 12.5 }} className="mono">
            {Object.entries(claimResult).map(([chName, results]) => (
              <div key={chName} style={{ marginBottom: 8 }}>
                <strong>{chName}:</strong>{' '}
                {Array.isArray(results)
                  ? results.map((r, i) => (
                      <span key={i} style={{ marginRight: 10 }}>
                        {r.faucet || r.message}: <Badge status={r.status === 'success' ? 'success' : r.status === 'cooldown' ? 'pending' : 'failed'}>{r.status}</Badge>
                        {r.remaining_hours ? ` (${r.remaining_hours}h left)` : ''}
                      </span>
                    ))
                  : JSON.stringify(results)}
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card
        title="Configured Faucets"
        action={<button className="primary sm" onClick={openCreate}>+ New Faucet</button>}
      >
        {actionMessage && <div style={{ fontSize: 13, color: 'var(--rose)', marginBottom: 12 }}>{actionMessage}</div>}

        {initialLoad ? (
          <div className="table-scroll"><table><tbody><SkeletonRows rows={4} cols={5} /></tbody></table></div>
        ) : faucets.length === 0 ? (
          <EmptyState icon="◇" title="No faucets configured" hint="Add a faucet so wallets can auto-claim gas and tokens." />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Chain</th>
                  <th>Cooldown</th>
                  <th>Status</th>
                  <th>Tokens</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {faucets.map(f => {
                  const isOpen = expanded === f.id
                  const draft = tokenForms[f.id] || EMPTY_TOKEN_FORM
                  return (
                    <React.Fragment key={f.id}>
                      <tr>
                        <td>
                          <div style={{ fontWeight: 600 }}>{f.name}</div>
                          <div className="mono" style={{ fontSize: 11, color: 'var(--text-faint)', maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis' }}>{f.url}</div>
                        </td>
                        <td>{chainName(f.chain_id)}</td>
                        <td>{f.cooldown_hours}h</td>
                        <td>
                          <button className="ghost sm" onClick={() => toggleEnabled(f)}>
                            <Badge status={f.enabled ? 'active' : 'paused'}>{f.enabled ? 'enabled' : 'disabled'}</Badge>
                          </button>
                        </td>
                        <td>
                          <button className="ghost sm" onClick={() => setExpanded(isOpen ? null : f.id)}>
                            {f.tokens.length} token(s) {isOpen ? '▲' : '▼'}
                          </button>
                        </td>
                        <td style={{ display: 'flex', gap: 6 }}>
                          <button className="ghost sm" onClick={() => openEdit(f)}>Edit</button>
                          <button className="sm danger" onClick={() => deleteFaucet(f)}>Delete</button>
                        </td>
                      </tr>
                      {isOpen && (
                        <tr style={{ background: 'var(--bg)' }}>
                          <td colSpan={6}>
                            <div style={{ padding: '12px 8px', display: 'flex', flexDirection: 'column', gap: 10 }}>
                              {f.tokens.length > 0 && (
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                                  {f.tokens.map(t => (
                                    <span key={t.id} className="badge neutral" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                                      {t.token_symbol}: {t.amount_given}
                                      <button onClick={() => removeToken(t.id)} style={{ background: 'none', border: 'none', padding: 0, color: 'var(--rose)', cursor: 'pointer', fontSize: 13 }}>✕</button>
                                    </span>
                                  ))}
                                </div>
                              )}
                              <div style={{ fontSize: 12, color: 'var(--text-faint)' }}>
                                Add a token this faucet gives out (e.g. USDC, USDT, DAI, or the chain's gas token):
                              </div>
                              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                                <input placeholder="Symbol (USDC)" value={draft.token_symbol}
                                  onChange={e => setTokenForms(prev => ({ ...prev, [f.id]: { ...draft, token_symbol: e.target.value } }))}
                                  style={{ width: 100 }} />
                                <input placeholder="Contract address (blank = native)" value={draft.token_contract}
                                  onChange={e => setTokenForms(prev => ({ ...prev, [f.id]: { ...draft, token_contract: e.target.value } }))}
                                  style={{ width: 240 }} className="mono" />
                                <input placeholder="Amount given" type="number" value={draft.amount_given}
                                  onChange={e => setTokenForms(prev => ({ ...prev, [f.id]: { ...draft, amount_given: e.target.value } }))}
                                  style={{ width: 110 }} />
                                <input placeholder="Decimals" type="number" value={draft.decimals}
                                  onChange={e => setTokenForms(prev => ({ ...prev, [f.id]: { ...draft, decimals: e.target.value } }))}
                                  style={{ width: 80 }} />
                                <button className="ghost sm" onClick={() => addToken(f.id)}>+ Add Token</button>
                              </div>
                              {f.fallback_urls && f.fallback_urls.length > 0 && (
                                <div style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>
                                  Fallback URLs: {f.fallback_urls.join(', ')}
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

      {showForm && (
        <Card title={form.id ? 'Edit Faucet' : 'New Faucet'}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxWidth: 520 }}>
            <input placeholder="Name" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
            <select value={form.chain_id} onChange={e => setForm({ ...form, chain_id: e.target.value })}>
              <option value="">— Any chain (project-level faucet) —</option>
              {chains.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <input placeholder="Faucet URL (https://...)" value={form.url} onChange={e => setForm({ ...form, url: e.target.value })} className="mono" />
            <textarea placeholder="Fallback URLs, one per line" value={form.fallback_urls}
              onChange={e => setForm({ ...form, fallback_urls: e.target.value })} rows={2} className="mono" />
            <textarea placeholder='Body template JSON, e.g. {"address": "{address}"}' value={form.body_template}
              onChange={e => setForm({ ...form, body_template: e.target.value })} rows={2} className="mono" />
            <div style={{ display: 'flex', gap: 10 }}>
              <select value={form.method} onChange={e => setForm({ ...form, method: e.target.value })} style={{ width: 110 }}>
                <option value="POST">POST</option>
                <option value="GET">GET</option>
              </select>
              <input type="number" placeholder="Cooldown hours" value={form.cooldown_hours}
                onChange={e => setForm({ ...form, cooldown_hours: e.target.value })} style={{ width: 140 }} />
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
                <input type="checkbox" checked={form.enabled} onChange={e => setForm({ ...form, enabled: e.target.checked })} />
                Enabled
              </label>
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
              <button className="primary" onClick={saveFaucet} disabled={loading}>
                {loading ? <Spinner inline size={14} /> : 'Save Faucet'}
              </button>
              <button className="ghost" onClick={() => setShowForm(false)}>Cancel</button>
            </div>
          </div>
        </Card>
      )}
    </div>
  )
}
