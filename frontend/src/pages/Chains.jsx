import React, { useEffect, useState } from 'react'
import api from '../api'
import { Card, Badge, EmptyState } from '../components/ui'
import { useConfirm } from '../components/Confirm'

const EMPTY = { name: '', chain_id: '', rpc_urls: '', gas_token_symbol: 'ETH', gas_token_is_native: true }
const EMPTY_TOKEN = { symbol: '', contract_address: '', decimals: 18, coingecko_id: '' }
const err = e => e?.response?.data?.detail || 'Request failed.'

function ChainPanel({ c, onSaved }) {
  const [f, setF] = useState({
    name: c.name, explorer_url: c.explorer_url || '', rpc_urls: (c.rpc_urls || []).join('\n'),
    gas_token_symbol: c.gas_token_symbol, coingecko_id: c.coingecko_id || '', gas_token_is_native: c.gas_token_is_native,
    gas_token_contract: c.gas_token_contract || '', gas_token_decimals: c.gas_token_decimals,
    min_gas_balance_warning: c.min_gas_balance_warning, min_gas_balance_critical: c.min_gas_balance_critical,
    rpc_rate_limit_per_sec: c.rpc_rate_limit_per_sec, enabled: c.enabled,
  })
  const [rpc, setRpc] = useState(null)
  const [gas, setGas] = useState(null)
  const [tokens, setTokens] = useState([])
  const [tf, setTf] = useState(EMPTY_TOKEN)
  const [msg, setMsg] = useState('')
  const set = p => setF(x => ({ ...x, ...p }))

  const loadTokens = () => api.get(`/chains/${c.id}/tokens`).then(r => setTokens(r.data)).catch(() => {})
  useEffect(() => { loadTokens() }, [])

  const save = async () => {
    setMsg('')
    const urls = f.rpc_urls.split('\n').map(s => s.trim()).filter(Boolean)
    if (!urls.length) return setMsg('At least one RPC URL is required.')
    try {
      await api.put(`/chains/${c.id}`, {
        ...f, rpc_urls: urls, explorer_url: f.explorer_url || null, coingecko_id: f.coingecko_id.trim() || null,
        gas_token_contract: f.gas_token_is_native ? null : (f.gas_token_contract || null),
        gas_token_decimals: Number(f.gas_token_decimals),
        min_gas_balance_warning: Number(f.min_gas_balance_warning),
        min_gas_balance_critical: Number(f.min_gas_balance_critical),
        rpc_rate_limit_per_sec: Number(f.rpc_rate_limit_per_sec),
      })
      setMsg('Saved.'); onSaved()
    } catch (e) { setMsg(err(e)) }
  }
  const testRpc = async () => { setRpc('testing…'); try { setRpc((await api.post(`/chains/${c.id}/test-rpc`)).data) } catch (e) { setRpc(err(e)) } }
  const loadGas = async () => { setGas('loading…'); try { setGas((await api.get(`/ops/chains/${c.id}/gas`)).data) } catch (e) { setGas(err(e)) } }
  const addToken = async () => {
    if (!tf.symbol || !tf.contract_address) return setMsg('Symbol and contract address are required.')
    try {
      await api.post(`/chains/${c.id}/tokens`, {
        chain_id: c.id, symbol: tf.symbol.toUpperCase(), contract_address: tf.contract_address,
        decimals: Number(tf.decimals), coingecko_id: tf.coingecko_id || null,
      })
      setTf(EMPTY_TOKEN); loadTokens()
    } catch (e) { setMsg(err(e)) }
  }

  return (
    <div style={{ gridColumn: '1 / -1', display: 'flex', flexDirection: 'column', gap: 12, paddingTop: 10, borderTop: '1px solid var(--border)' }}>
      <input placeholder="Name" value={f.name} onChange={e => set({ name: e.target.value })} />
      <textarea className="mono" rows={3} placeholder="RPC URLs, one per line (first = primary, rest = fallbacks)" value={f.rpc_urls} onChange={e => set({ rpc_urls: e.target.value })} />
      <input placeholder="Explorer URL" value={f.explorer_url} onChange={e => set({ explorer_url: e.target.value })} />
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <input placeholder="Gas symbol" value={f.gas_token_symbol} onChange={e => set({ gas_token_symbol: e.target.value })} style={{ width: 90 }} />
        <input title="CoinGecko API id used for USD prices, e.g. ethereum, binancecoin, matic-network. Leave blank to guess from the symbol." placeholder="CoinGecko id (optional)" value={f.coingecko_id} onChange={e => set({ coingecko_id: e.target.value })} style={{ width: 170 }} />
        <label style={{ fontSize: 13, display: 'flex', gap: 6, alignItems: 'center' }}>
          <input type="checkbox" checked={f.gas_token_is_native} onChange={e => set({ gas_token_is_native: e.target.checked })} style={{ width: 'auto' }} /> native
        </label>
        {!f.gas_token_is_native && <input className="mono" placeholder="Gas token contract" value={f.gas_token_contract} onChange={e => set({ gas_token_contract: e.target.value })} style={{ width: 260 }} />}
        <input type="number" title="gas token decimals" value={f.gas_token_decimals} onChange={e => set({ gas_token_decimals: e.target.value })} />
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', fontSize: 12.5, color: 'var(--text-dim)' }}>
        warn below <input type="number" step="any" value={f.min_gas_balance_warning} onChange={e => set({ min_gas_balance_warning: e.target.value })} style={{ width: 100 }} />
        critical below <input type="number" step="any" value={f.min_gas_balance_critical} onChange={e => set({ min_gas_balance_critical: e.target.value })} style={{ width: 100 }} />
        RPC req/sec <input type="number" value={f.rpc_rate_limit_per_sec} onChange={e => set({ rpc_rate_limit_per_sec: e.target.value })} />
        <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}><input type="checkbox" checked={f.enabled} onChange={e => set({ enabled: e.target.checked })} style={{ width: 'auto' }} /> enabled</label>
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button className="primary sm" onClick={save}>Save</button>
        <button className="sm" onClick={testRpc}>Test RPCs</button>
        <button className="sm" onClick={loadGas}>Gas status</button>
      </div>
      {msg && <div style={{ fontSize: 13, color: 'var(--text-dim)' }}>{msg}</div>}

      {rpc && (Array.isArray(rpc)
        ? <div className="mono" style={{ fontSize: 12 }}>{rpc.map((r, i) => <div key={i}>{r.status === 'ok' ? '✅' : '❌'} {r.url} {r.status === 'ok' ? `· ${Math.round(r.latency_ms)}ms · block ${r.block}` : `· ${r.error}`}</div>)}</div>
        : <div style={{ fontSize: 12 }}>{rpc}</div>)}

      {gas && (typeof gas === 'string' ? <div style={{ fontSize: 12 }}>{gas}</div> : (
        <div className="mono" style={{ fontSize: 12, color: 'var(--text-dim)' }}>
          now {gas.status.current_gwei} gwei · 6h avg {gas.status.average_6h_gwei} · ratio {gas.status.ratio}× {gas.status.is_spike ? '🔴 SPIKE' : '🟢 normal'} · {gas.status.samples_in_window} samples
          {gas.optimal_windows?.[0]?.hour_utc != null && <div>cheapest UTC hours: {gas.optimal_windows.slice(0, 4).map(w => `${w.hour_utc}:00 (${w.avg_gwei})`).join(', ')}</div>}
        </div>
      ))}

      <div style={{ fontSize: 12, color: 'var(--text-faint)', textTransform: 'uppercase' }}>Token registry</div>
      {tokens.length > 0 && <div className="mono" style={{ fontSize: 12 }}>{tokens.map(t => <div key={t.id}>{t.symbol} · {t.decimals} dec · {t.contract_address}</div>)}</div>}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <input placeholder="Symbol" value={tf.symbol} onChange={e => setTf({ ...tf, symbol: e.target.value })} style={{ width: 90 }} />
        <input className="mono" placeholder="Contract 0x…" value={tf.contract_address} onChange={e => setTf({ ...tf, contract_address: e.target.value })} style={{ width: 260 }} />
        <input type="number" value={tf.decimals} onChange={e => setTf({ ...tf, decimals: e.target.value })} />
        <input placeholder="coingecko id" value={tf.coingecko_id} onChange={e => setTf({ ...tf, coingecko_id: e.target.value })} style={{ width: 130 }} />
        <button className="ghost sm" onClick={addToken}>+ Add token</button>
      </div>
    </div>
  )
}

export default function Chains() {
  const confirm = useConfirm()
  const [chains, setChains] = useState([])
  const [loaded, setLoaded] = useState(false)
  const [newChain, setNewChain] = useState(EMPTY)
  const [open, setOpen] = useState(null)
  const [msg, setMsg] = useState('')

  const fetchChains = () => api.get('/chains/').then(r => { setChains(r.data); setLoaded(true) }).catch(() => setLoaded(true))
  useEffect(() => { fetchChains() }, [])

  const add = async () => {
    if (!newChain.name || !newChain.chain_id) return
    setMsg('')
    try {
      await api.post('/chains/', { ...newChain, rpc_urls: newChain.rpc_urls.split(',').map(s => s.trim()).filter(Boolean), chain_id: Number(newChain.chain_id) })
      setNewChain(EMPTY); fetchChains()
    } catch (e) { setMsg(err(e)) }
  }
  const remove = async (c) => {
    if (!(await confirm({ title: `Delete chain “${c.name}”?`, message: 'Tasks, tokens and faucets that point at it will break.', confirmLabel: 'Delete chain', tone: 'danger' }))) return
    try { await api.delete(`/chains/${c.id}`); setOpen(null); fetchChains() } catch (e) { setMsg(err(e)) }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <Card title="Add chain">
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
          <input placeholder="Name" value={newChain.name} onChange={e => setNewChain({ ...newChain, name: e.target.value })} />
          <input placeholder="Chain ID" type="number" value={newChain.chain_id} onChange={e => setNewChain({ ...newChain, chain_id: e.target.value })} />
          <input placeholder="RPC URLs (comma sep)" value={newChain.rpc_urls} onChange={e => setNewChain({ ...newChain, rpc_urls: e.target.value })} style={{ minWidth: 220, flex: 1 }} />
          <input placeholder="Gas symbol" value={newChain.gas_token_symbol} onChange={e => setNewChain({ ...newChain, gas_token_symbol: e.target.value })} style={{ width: 90 }} />
          <button className="primary" onClick={add}>Add chain</button>
        </div>
        {msg && <div className="error" style={{ marginTop: 10 }}>{msg}</div>}
      </Card>

      <Card title="Configured chains">
        {!loaded && <div className="skeleton" style={{ height: 70, borderRadius: 10 }} />}
        {loaded && chains.length === 0 && <EmptyState icon="⛓" title="No chains configured" hint="Add a chain above to start routing tasks to it." />}
        {loaded && chains.length > 0 && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px,1fr))', gap: 10 }}>
            {chains.map(c => (
              <div key={c.id} className="card" style={{ padding: 14, boxShadow: 'none', gridColumn: open === c.id ? '1 / -1' : undefined }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>{c.name}</span>
                  <Badge status={c.enabled}>{c.enabled ? 'Enabled' : 'Disabled'}</Badge>
                </div>
                <div style={{ fontSize: 12.5, color: 'var(--text-dim)', display: 'flex', flexDirection: 'column', gap: 3, marginBottom: 10 }}>
                  <span className="mono">Chain ID: {c.chain_id} · DB id {c.id}</span>
                  <span>Gas token: {c.gas_token_symbol} · {(c.rpc_urls || []).length} RPC(s)</span>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button className="sm" onClick={() => setOpen(open === c.id ? null : c.id)}>{open === c.id ? 'Close' : 'Manage'}</button>
                  <button className="sm danger" onClick={() => remove(c)}>Delete</button>
                </div>
                {open === c.id && <ChainPanel c={c} onSaved={fetchChains} />}
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
