import React, { useEffect, useState, useCallback } from 'react'
import { Link, useParams } from 'react-router-dom'
import api from '../api'
import { Card, Badge, EmptyState } from '../components/ui'
import { useConfirm } from '../components/Confirm'

const err = e => e?.response?.data?.detail || 'Request failed.'
const CRIT_TYPES = ['tx_count', 'volume', 'time', 'social', 'token_hold', 'governance', 'other']
const EMPTY_C = { type: 'tx_count', description: '', threshold: '', unit: '', uncertain: false }

export default function ProjectDetail() {
  const confirm = useConfirm()
  const { id } = useParams()
  const [p, setP] = useState(null)
  const [f, setF] = useState(null)
  const [criteria, setCriteria] = useState([])
  const [nc, setNc] = useState(EMPTY_C)
  const [edit, setEdit] = useState(null)   // {id, ...fields}
  const [msg, setMsg] = useState('')

  const load = useCallback(async () => {
    try {
      const pr = (await api.get(`/projects/${id}`)).data
      setP(pr)
      setF({
        priority: pr.priority ?? 5, max_concurrent_wallets: pr.max_concurrent_wallets ?? 2,
        website: pr.website || '', twitter: pr.twitter || '', discord: pr.discord || '', notes: pr.notes || '',
        tge_date: pr.tge_date || '', airdrop_date: pr.airdrop_date || '',
      })
      setCriteria((await api.get(`/ops/projects/${id}/criteria`)).data)
    } catch (e) { setMsg(err(e)) }
  }, [id])
  useEffect(() => { load() }, [load])

  const act = async (fn, ok) => {
    setMsg('')
    try { const r = await fn(); setMsg(ok || r?.data?.message || 'Done.'); await load() } catch (e) { setMsg(err(e)) }
  }
  const set = x => setF(v => ({ ...v, ...x }))

  if (!p || !f) return <Card title="Project">{msg ? <p className="error">{msg}</p> : <div className="skeleton" style={{ height: 80 }} />}</Card>

  const saveDetails = () => act(() => api.put(`/ops/projects/${id}/details`, {
    priority: Number(f.priority), max_concurrent_wallets: Number(f.max_concurrent_wallets),
    website: f.website, twitter: f.twitter, discord: f.discord, notes: f.notes,
    tge_date: f.tge_date, airdrop_date: f.airdrop_date,
  }))
  const addCriterion = () => nc.description.trim() && act(async () => {
    const r = await api.post(`/ops/projects/${id}/criteria`, { ...nc, threshold: nc.threshold === '' ? null : Number(nc.threshold), unit: nc.unit || null })
    setNc(EMPTY_C); return r
  }, 'Criterion added.')
  const saveEdit = () => act(async () => {
    const { id: cid, ...rest } = edit
    const r = await api.put(`/ops/criteria/${cid}`, { ...rest, threshold: rest.threshold === '' || rest.threshold == null ? undefined : Number(rest.threshold) })
    setEdit(null); return r
  }, 'Criterion updated.')

  const lbl = { display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: 'var(--text-dim)' }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <Link to="/projects" style={{ fontSize: 13 }}>← Projects</Link>
        <h2 style={{ fontSize: 18 }}>{p.name}</h2>
        <Badge status={p.status === 'active' ? 'active' : p.status === 'stopped' || p.status === 'archived' ? 'failed' : p.status}>{p.status}</Badge>
        <Badge status={p.eligibility_status === 'eligible' ? 'success' : p.eligibility_status === 'not_eligible' ? 'failed' : 'neutral'}>{p.eligibility_status || 'pending'}</Badge>
      </div>
      {msg && <div style={{ fontSize: 13, color: 'var(--text-dim)' }}>{msg}</div>}

      <Card title="Details and limits">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12 }}>
          <label style={lbl}>Priority (1–10)<input type="number" min={1} max={10} value={f.priority} onChange={e => set({ priority: e.target.value })} /></label>
          <label style={lbl}>Max concurrent wallets<input type="number" min={1} value={f.max_concurrent_wallets} onChange={e => set({ max_concurrent_wallets: e.target.value })} /></label>
          <label style={lbl}>TGE date<input type="date" value={f.tge_date} onChange={e => set({ tge_date: e.target.value })} /></label>
          <label style={lbl}>Airdrop / snapshot date<input type="date" value={f.airdrop_date} onChange={e => set({ airdrop_date: e.target.value })} /></label>
          <label style={lbl}>Website<input value={f.website} onChange={e => set({ website: e.target.value })} /></label>
          <label style={lbl}>Twitter / X<input value={f.twitter} onChange={e => set({ twitter: e.target.value })} /></label>
          <label style={lbl}>Discord<input value={f.discord} onChange={e => set({ discord: e.target.value })} /></label>
        </div>
        <textarea rows={3} placeholder="Notes" value={f.notes} onChange={e => set({ notes: e.target.value })} style={{ width: '100%', marginTop: 12 }} />
        <div style={{ display: 'flex', gap: 8, marginTop: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <button className="primary sm" onClick={saveDetails}>Save</button>
          <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>Dates feed the Snapshot Calendar.</span>
        </div>
      </Card>

      <Card title="Circuit breaker">
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap', fontSize: 13 }}>
          <Badge status={p.circuit_breaker_active ? 'failed' : 'active'}>{p.circuit_breaker_active ? 'tripped' : 'ok'}</Badge>
          <span className="mono">{p.consecutive_failures ?? 0}/5 consecutive failures</span>
          {(p.circuit_breaker_active || p.consecutive_failures > 0) && (
            <button className="sm" onClick={() => act(() => api.post(`/ops/projects/${id}/reset-circuit`))}>Reset</button>
          )}
        </div>
      </Card>

      <Card title="Eligibility criteria">
        {criteria.length === 0 ? <EmptyState icon="◇" title="No criteria yet" hint="Add one below, or draft them from docs via Projects → Draft criteria." /> : (
          <div className="table-scroll"><table>
            <thead><tr><th>Type</th><th>Description</th><th>Threshold</th><th>Source</th><th></th></tr></thead>
            <tbody>
              {criteria.map(c => edit?.id === c.id ? (
                <tr key={c.id}>
                  <td><select value={edit.type} onChange={e => setEdit({ ...edit, type: e.target.value })}>{CRIT_TYPES.map(t => <option key={t}>{t}</option>)}</select></td>
                  <td><input value={edit.description} onChange={e => setEdit({ ...edit, description: e.target.value })} style={{ width: '100%' }} /></td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <input type="number" step="any" value={edit.threshold ?? ''} onChange={e => setEdit({ ...edit, threshold: e.target.value })} style={{ width: 80 }} />{' '}
                    <input value={edit.unit || ''} onChange={e => setEdit({ ...edit, unit: e.target.value })} style={{ width: 70 }} />
                  </td>
                  <td><label style={{ fontSize: 12 }}><input type="checkbox" style={{ width: 'auto' }} checked={!!edit.uncertain} onChange={e => setEdit({ ...edit, uncertain: e.target.checked })} /> uncertain</label></td>
                  <td style={{ whiteSpace: 'nowrap' }}><button className="primary sm" onClick={saveEdit}>Save</button> <button className="ghost sm" onClick={() => setEdit(null)}>Cancel</button></td>
                </tr>
              ) : (
                <tr key={c.id}>
                  <td><span className="badge neutral">{c.type}</span></td>
                  <td style={{ fontSize: 13 }}>{c.description}{c.uncertain && <span style={{ color: 'var(--amber)', marginLeft: 6, fontSize: 11 }}>⚠ uncertain</span>}</td>
                  <td className="mono">{c.threshold ?? '—'} {c.unit || ''}</td>
                  <td style={{ fontSize: 12, color: 'var(--text-faint)' }}>{c.ai_extracted ? 'AI draft' : 'manual'}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <button className="ghost sm" onClick={() => setEdit({ id: c.id, type: c.type, description: c.description, threshold: c.threshold, unit: c.unit, uncertain: c.uncertain })}>Edit</button>{' '}
                    <button className="sm danger" onClick={async () => (await confirm({ title: 'Delete this criterion?', confirmLabel: 'Delete', tone: 'danger' })) && act(() => api.delete(`/ops/criteria/${c.id}`))}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 14 }}>
          <select value={nc.type} onChange={e => setNc({ ...nc, type: e.target.value })}>{CRIT_TYPES.map(t => <option key={t}>{t}</option>)}</select>
          <input placeholder="Description" value={nc.description} onChange={e => setNc({ ...nc, description: e.target.value })} style={{ flex: 1, minWidth: 220 }} />
          <input type="number" step="any" placeholder="Threshold" value={nc.threshold} onChange={e => setNc({ ...nc, threshold: e.target.value })} style={{ width: 100 }} />
          <input placeholder="Unit" value={nc.unit} onChange={e => setNc({ ...nc, unit: e.target.value })} style={{ width: 80 }} />
          <button className="primary sm" onClick={addCriterion}>Add</button>
        </div>
      </Card>
    </div>
  )
}
