import React, { useEffect, useState } from 'react'
import api from '../api'
import { apiError } from '../hooks/useApi'
import { useToast } from './Toast'
import { useConfirm } from './Confirm'
import { Modal, Badge, Field } from './ui'

// [key, label, nullable]. Blank NULLABLE fields are sent as null (= clear the override);
// blank REQUIRED fields are left out so the server keeps their value. Sending null for a
// required field used to hit a NOT NULL column and return a 500.
const NUM_FIELDS = [
  ['amount_min_override', 'Amount min override', true], ['amount_max_override', 'Amount max override', true],
  ['active_hour_start', 'Active from (UTC hour 0-23)', true], ['active_hour_end', 'Active until (UTC hour 0-23)', true],
  ['start_offset_max_mins', 'Start offset max (min)', false], ['sleep_min_mins', 'Sleep min (min)', false],
  ['sleep_max_mins', 'Sleep max (min)', false], ['gas_multiplier', 'Gas multiplier (0.5-3.0)', false],
  ['daily_tx_min', 'Daily tx min', false], ['daily_tx_max', 'Daily tx max', false],
]

/** Wallet manager — opens as a modal (a bottom sheet on phones). */
export default function WalletManage({ wallet, onChanged, onClose }) {
  const toast = useToast()
  const confirm = useConfirm()
  const id = wallet?.id
  const [tags, setTags] = useState('')
  const [s, setS] = useState(null)
  const [nonces, setNonces] = useState([])
  const [chains, setChains] = useState([])

  const loadSettings = () => api.get(`/wallets/${id}/settings`).then(r => setS(r.data)).catch(() => setS({}))
  const loadNonces = () => api.get(`/ops/wallets/${id}/nonces`).then(r => setNonces(r.data)).catch(() => {})

  useEffect(() => {
    if (!id) return
    setTags((wallet.tags || []).join(', ')); setS(null)
    loadSettings()
    api.get('/chains/').then(r => setChains(r.data)).catch(() => {})
    loadNonces()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  if (!wallet) return null
  const chainName = cid => chains.find(c => c.id === cid)?.name || `chain #${cid}`

  const act = async (fn, ok) => {
    try { const r = await fn(); toast.success(ok || r?.data?.message || 'Done.'); onChanged?.() }
    catch (e) { toast.error(apiError(e)) }
  }

  const saveSettings = () => {
    const payload = {
      amount_distribution: s.amount_distribution || 'weighted_low',
      amount_vary_daily: !!s.amount_vary_daily,
      bidirectional_default: !!s.bidirectional_default,
    }
    for (const [k, , nullable] of NUM_FIELDS) {
      const v = s[k]
      if (v === '' || v == null) { if (nullable) payload[k] = null } else payload[k] = Number(v)
    }
    return act(() => api.put(`/ops/wallets/${id}/settings`, payload).then(r => { loadSettings(); return r }), 'Settings saved.')
  }

  const reroll = async () => {
    if (await confirm({ title: 'Re-roll persona?', message: "Replaces this wallet's behaviour settings with a new random persona.", confirmLabel: 'Re-roll' }))
      act(() => api.post(`/ops/wallets/${id}/persona/reroll`).then(r => { loadSettings(); return r }))
  }

  const blacklist = async () => {
    if (await confirm({ title: `Blacklist wallet #${id}?`, message: 'The agent will never use it again until you change its status.', confirmLabel: 'Blacklist', tone: 'danger' }))
      act(() => api.put(`/wallets/${id}/status`, null, { params: { status: 'blacklisted' } }), 'Blacklisted.')
  }

  return (
    <Modal title={`Manage wallet #${id}`} onClose={onClose} width={720}>
      <div className="stack" style={{ gap: 18, marginTop: 10 }}>
        <div className="row">
          <Badge status={wallet.status}>{wallet.status}</Badge>
          <span className="muted" style={{ fontSize: 12 }}>failures: {wallet.failure_count ?? 0}</span>
          {['cooldown', 'paused'].includes(wallet.status) && (
            <button className="primary sm" onClick={() => act(() => api.post(`/ops/wallets/${id}/recover`))}>Recover (active + reset failures)</button>
          )}
          {wallet.status !== 'blacklisted' && <button className="sm danger" onClick={blacklist}>Blacklist</button>}
          <button className="sm" onClick={() => act(() => api.put(`/wallets/${id}/gas-wallet`, null, { params: { is_gas: !wallet.is_gas_wallet } }), wallet.is_gas_wallet ? 'No longer a gas wallet.' : 'Marked as gas wallet.')}>
            {wallet.is_gas_wallet ? 'Unset gas wallet' : 'Set as gas wallet'}
          </button>
        </div>

        <div className="row" style={{ flexWrap: 'nowrap' }}>
          <input className="grow" placeholder="tags, comma separated" value={tags} onChange={e => setTags(e.target.value)} />
          <button className="sm" onClick={() => act(() => api.put(`/ops/wallets/${id}/tags`, { tags: tags.split(',') }), 'Tags saved.')}>Save tags</button>
        </div>

        <div>
          <div className="eyebrow" style={{ marginBottom: 8 }}>Persona / behaviour settings</div>
          {!s ? <div className="skeleton" style={{ height: 50 }} /> : (
            <>
              <div className="grid-fields">
                {NUM_FIELDS.map(([k, label]) => (
                  <Field key={k} label={label}>
                    <input type="number" inputMode="decimal" step="any" value={s[k] ?? ''} onChange={e => setS({ ...s, [k]: e.target.value })} />
                  </Field>
                ))}
                <Field label="Amount distribution">
                  <select value={s.amount_distribution || 'weighted_low'} onChange={e => setS({ ...s, amount_distribution: e.target.value })}>
                    <option value="weighted_low">weighted low</option>
                    <option value="weighted_high">weighted high</option>
                    <option value="uniform">uniform</option>
                  </select>
                </Field>
              </div>
              <div className="row" style={{ gap: 18, margin: '12px 0' }}>
                <label className="check"><input type="checkbox" checked={!!s.amount_vary_daily} onChange={e => setS({ ...s, amount_vary_daily: e.target.checked })} /> vary amounts daily</label>
                <label className="check"><input type="checkbox" checked={!!s.bidirectional_default} onChange={e => setS({ ...s, bidirectional_default: e.target.checked })} /> bidirectional by default</label>
              </div>
              <div className="row">
                <button className="primary sm" onClick={saveSettings}>Save settings</button>
                <button className="sm" onClick={reroll}>Re-roll persona</button>
              </div>
            </>
          )}
        </div>

        <div>
          <div className="eyebrow" style={{ marginBottom: 8 }}>Nonces</div>
          {nonces.length === 0 ? <span className="faint" style={{ fontSize: 12.5 }}>No nonce records yet.</span> : nonces.map(n => (
            <div key={n.chain_id} className="row" style={{ fontSize: 12.5, marginBottom: 8 }}>
              <span style={{ minWidth: 110 }}>{chainName(n.chain_id)}</span>
              <span className="mono">nonce {n.nonce}</span>
              <Badge status={n.locked ? 'pending' : 'active'}>{n.locked ? 'locked' : 'free'}</Badge>
              {n.locked && <button className="sm" onClick={() => act(() => api.post(`/ops/wallets/${id}/nonces/${n.chain_id}/release`).then(r => { loadNonces(); return r }))}>Release lock</button>}
              <button className="ghost sm" onClick={() => act(() => api.post(`/ops/wallets/${id}/nonces/${n.chain_id}/sync`).then(r => { loadNonces(); return r }))}>Sync from chain</button>
            </div>
          ))}
        </div>

        <div className="modal-actions" style={{ marginTop: 0 }}><button onClick={onClose}>Close</button></div>
      </div>
    </Modal>
  )
}
