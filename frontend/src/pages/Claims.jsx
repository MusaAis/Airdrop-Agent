import React, { useState, useEffect, useCallback } from 'react'
import { API_BASE } from '../api'

export default function Claims({ token }) {
  const [eligible, setEligible] = useState([])
  const [pending,  setPending]  = useState([])
  const [threshold, setThr]     = useState(50)
  const [msg, setMsg]           = useState('')
  const h = { Authorization: `Bearer ${token}` }

  const load = useCallback(async () => {
    try {
      const [e, p] = await Promise.all([
        fetch(`${API_BASE}/claims/eligible`, { headers: h }).then(r => r.json()),
        fetch(`${API_BASE}/claims/pending`,  { headers: h }).then(r => r.json()),
      ])
      setEligible(Array.isArray(e) ? e : []); setPending(Array.isArray(p) ? p : [])
    } catch {}
  }, [token])

  useEffect(() => { load() }, [load])

  const claim = async (wid, pid) => {
    if (!window.confirm('Trigger claim now?')) return
    const d = await fetch(`${API_BASE}/claims/trigger`, { method: 'POST', headers: { ...h, 'Content-Type': 'application/json' }, body: JSON.stringify({ wallet_id: wid, project_id: pid }) }).then(r => r.json())
    setMsg(d.message || 'Done'); load()
  }

  const saveThreshold = async () => {
    await fetch(`${API_BASE}/claims/threshold`, { method: 'POST', headers: { ...h, 'Content-Type': 'application/json' }, body: JSON.stringify({ usd: threshold }) })
    setMsg(`Threshold saved: $${threshold}`)
  }

  const card = { background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: 10, padding: '14px 18px', marginBottom: 10 }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>Claim Management</h2>
        <button onClick={load} style={{ padding: '7px 16px', borderRadius: 8, background: 'var(--bg-elevated)', border: '1px solid var(--border)', color: 'var(--text)', cursor: 'pointer' }}>Refresh</button>
      </div>

      {msg && <div style={{ ...card, background: 'color-mix(in srgb,var(--signal) 12%,transparent)', borderColor: 'var(--signal)', fontSize: 13 }}>{msg}</div>}

      <div style={card}>
        <div style={{ fontWeight: 600, marginBottom: 10 }}>Auto-claim Threshold</div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Auto-claim below $</span>
          <input type="number" value={threshold} onChange={e => setThr(e.target.value)} style={{ width: 80, padding: '5px 8px', borderRadius: 6, border: '1px solid var(--border)', background: 'var(--bg)', color: 'var(--text)', fontSize: 13 }} />
          <button onClick={saveThreshold} style={{ padding: '5px 14px', borderRadius: 6, background: 'var(--signal)', border: 'none', color: '#06151A', fontWeight: 600, cursor: 'pointer' }}>Save</button>
        </div>
      </div>

      <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 10, marginTop: 16 }}>⏳ Pending High-Value Claims</div>
      {pending.length === 0 ? <div style={{ ...card, color: 'var(--text-secondary)', fontSize: 13 }}>None pending.</div>
        : pending.map((c, i) => (
          <div key={i} style={{ ...card, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontWeight: 600 }}>{c.project_name || `Project ${c.project_id}`}</div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Wallet {c.wallet_id} · Est. ${Number(c.estimated_usd||0).toFixed(2)}</div>
            </div>
            <button onClick={() => claim(c.wallet_id, c.project_id)} style={{ padding: '6px 16px', borderRadius: 7, background: 'var(--signal)', border: 'none', color: '#06151A', fontWeight: 700, cursor: 'pointer', fontSize: 13 }}>Claim</button>
          </div>
        ))
      }

      <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 10, marginTop: 16 }}>✅ All Eligible Wallets</div>
      {eligible.length === 0 ? <div style={{ ...card, color: 'var(--text-secondary)', fontSize: 13 }}>No eligible claims.</div>
        : eligible.map((c, i) => (
          <div key={i} style={card}>
            <div style={{ fontWeight: 600 }}>{c.project || `Project ${c.project_id}`}</div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Wallet {c.wallet_id} · {c.eligibility_pct}% eligible · ${Number(c.estimated_usd||0).toFixed(2)}</div>
          </div>
        ))
      }
    </div>
  )
}
