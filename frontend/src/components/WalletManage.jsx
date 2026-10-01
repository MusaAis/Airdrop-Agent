import React, { useEffect, useState } from 'react'
import api from '../api'
import { Card, Badge } from './ui'

const err = e => e?.response?.data?.detail || 'Request failed.'
const num = v => (v === '' || v == null ? null : Number(v))

const NUM_FIELDS = [
  ['amount_min_override', 'Amount min override'], ['amount_max_override', 'Amount max override'],
  ['active_hour_start', 'Active from (UTC hour)'], ['active_hour_end', 'Active until (UTC hour)'],
  ['start_offset_max_mins', 'Start offset max (min)'], ['sleep_min_mins', 'Sleep min (min)'],
  ['sleep_max_mins', 'Sleep max (min)'], ['gas_multiplier', 'Gas multiplier'],
  ['daily_tx_min', 'Daily tx min'], ['daily_tx_max', 'Daily tx max'],
]

export default function WalletManage({ wallet, onChanged, onClose }) {
  const id = wallet?.id
  const [tags, setTags] = useState('')
  const [s, setS] = useState(null)
  const [nonces, setNonces] = useState([])
  const [chains, setChains] = useState([])
  const [msg, setMsg] = useState('')

  const loadNonces = () => api.get(`/ops/wallets/${id}/nonces`).then(r => setNonces(r.data)).catch(() => {})

  useEffect(() => {
    if (!id) return
    setMsg(''); setTags((wallet.tags || []).join(', ')); setS(null)
    api.get(`/wallets/${id}/settings`).then(r => setS(r.data)).catch(() => setS({}))
    api.get('/chains/').then(r => setChains(r.data)).catch(() => {})
    loadNonces()
  }, [id])

  if (!wallet) return null
  const chainName = cid => chains.find(c => c.id === cid)?.name || `chain #${cid}`

  const act = async (fn, ok) => {
    setMsg('')
    try { const r = await fn(); setMsg(ok || r?.data?.message || 'Done.'); onChanged?.() } catch (e) { setMsg(err(e)) }
  }

  const saveSettings = () => act(() => api.put(`/wallets/${id}/settings`, {
    ...Object.fromEntries(NUM_FIELDS.map(([k]) => [k, num(s[k])])),
    amount_distribution: s.amount_distribution || 'weighted_low',
    amount_vary_daily: !!s.amount_vary_daily,
    bidirectional_default: !!s.bidirectional_default,
  }), 'Settings saved.')

  return (
    <Card title={`Manage wallet #${id}`} action={<button className="ghost sm" onClick={onClose}>Close</button>}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <Badge status={wallet.status}>{wallet.status}</Badge>
          <span style={{ fontSize: 12, color: 'var(--text-dim)' }}>failures: {wallet.failure_count ?? 0}</span>
          {['cooldown', 'paused'].includes(wallet.status) && (
            <button className="primary sm" onClick={() => act(() => api.post(`/ops/wallets/${id}/recover`))}>Recover (active + reset failures)</button>
          )}
          {wallet.status !== 'blacklisted' && (
            <button className="sm danger" onClick={() => window.confirm('Blacklist this wallet?') && act(() => api.put(`/wallets/${id}/status`, null, { params: { status: 'blacklisted' } }), 'Blacklisted.')}>Blacklist</button>
          )}
          <button className="sm" onClick={() => act(() => api.put(`/wallets/${id}/gas-wallet`, null, { params: { is_gas: !wallet.is_gas_wallet } }), wallet.is_gas_wallet ? 'No longer a gas wallet.' : 'Marked as gas wallet.')}>
            {wallet.is_gas_wallet ? 'Unset gas wallet' : 'Set as gas wallet'}
          </button>
        </div>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <input placeholder="tags, comma separated" value={tags} onChange={e => setTags(e.target.value)} style={{ flex: 1, minWidth: 220 }} />
          <button className="sm" onClick={() => act(() => api.put(`/ops/wallets/${id}/tags`, { tags: tags.split(',') }), 'Tags saved.')}>Save tags</button>
        </div>

        <div>
          <div style={{ fontSize: 11, color: 'var(--text-faint)', textTransform: 'uppercase', marginBottom: 8 }}>Persona / behaviour settings</div>
          {!s ? <div className="skeleton" style={{ height: 50 }} /> : (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))', gap: 10 }}>
                {NUM_FIELDS.map(([k, label]) => (
                  <label key={k} style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: 'var(--text-dim)' }}>
                    {label}
                    <input type="number" step="any" value={s[k] ?? ''} onChange={e => setS({ ...s, [k]: e.target.value })} style={{ width: '100%' }} />
                  </label>
                ))}
                <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: 'var(--text-dim)' }}>
                  Amount distribution
                  <select value={s.amount_distribution || 'weighted_low'} onChange={e => setS({ ...s, amount_distribution: e.target.value })}>
                    <option value="weighted_low">weighted low</option><option value="weighted_high">weighted high</option><option value="uniform">uniform</option>
                  </select>
                </label>
              </div>
              <div style={{ display: 'flex', gap: 16, margin: '10px 0', fontSize: 13 }}>
                <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}><input type="checkbox" style={{ width: 'auto' }} checked={!!s.amount_vary_daily} onChange={e => setS({ ...s, amount_vary_daily: e.target.checked })} /> vary amounts daily</label>
                <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}><input type="checkbox" style={{ width: 'auto' }} checked={!!s.bidirectional_default} onChange={e => setS({ ...s, bidirectional_default: e.target.checked })} /> bidirectional by default</label>
              </div>
              <button className="primary sm" onClick={saveSettings}>Save settings</button>
            </>
          )}
        </div>

        <div>
          <div style={{ fontSize: 11, color: 'var(--text-faint)', textTransform: 'uppercase', marginBottom: 8 }}>Nonces</div>
          {nonces.length === 0 ? <span style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>No nonce records yet.</span> : nonces.map(n => (
            <div key={n.chain_id} style={{ display: 'flex', gap: 10, alignItems: 'center', fontSize: 12.5, marginBottom: 6, flexWrap: 'wrap' }}>
              <span style={{ minWidth: 120 }}>{chainName(n.chain_id)}</span>
              <span className="mono">nonce {n.nonce}</span>
              <Badge status={n.locked ? 'pending' : 'active'}>{n.locked ? 'locked' : 'free'}</Badge>
              {n.locked && <button className="sm" onClick={() => act(() => api.post(`/ops/wallets/${id}/nonces/${n.chain_id}/release`).then(r => { loadNonces(); return r }))}>Release lock</button>}
              <button className="ghost sm" onClick={() => act(() => api.post(`/ops/wallets/${id}/nonces/${n.chain_id}/sync`).then(r => { loadNonces(); return r }))}>Sync from chain</button>
            </div>
          ))}
        </div>

        {msg && <div style={{ fontSize: 13, color: 'var(--text-dim)' }}>{msg}</div>}
      </div>
    </Card>
  )
}
