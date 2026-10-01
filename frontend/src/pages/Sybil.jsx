import React, { useState, useEffect, useCallback } from 'react'
import { API_BASE } from '../api'

const riskColor = r => ({ critical:'#ef4444', high:'#f97316', medium:'#f59e0b', low:'var(--signal)' }[r] || 'var(--text-secondary)')

export default function Sybil({ token }) {
  const [pairs, setPairs]   = useState([])
  const [wallets, setWallets] = useState([])
  const h = { Authorization: `Bearer ${token}` }

  const load = useCallback(async () => {
    try {
      const [s, w] = await Promise.all([
        fetch(`${API_BASE}/reports/sybil`, { headers: h }).then(r => r.json()),
        fetch(`${API_BASE}/wallets/`,        { headers: h }).then(r => r.json()),
      ])
      setPairs(Array.isArray(s) ? s : (s.suspicious_pairs || [])); setWallets(Array.isArray(w) ? w : [])
    } catch {}
  }, [token])

  useEffect(() => { load() }, [load])

  const card = { background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: 10, padding: '14px 18px', marginBottom: 10 }
  const addr = id => { const w = wallets.find(x => x.id === id); return w ? w.address.slice(0,10)+'…' : `W${id}` }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>Sybil Risk Dashboard</h2>
        <button onClick={load} style={{ padding: '7px 16px', borderRadius: 8, background: 'var(--bg-elevated)', border: '1px solid var(--border)', color: 'var(--text)', cursor: 'pointer' }}>Refresh</button>
      </div>

      {/* Wallet health grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(200px,1fr))', gap: 12, marginBottom: 28 }}>
        {wallets.map(w => (
          <div key={w.id} style={{ ...card, marginBottom: 0 }}>
            <div style={{ fontSize: 12, fontFamily: 'monospace', color: 'var(--text-secondary)', marginBottom: 4 }}>{w.address.slice(0,14)}…</div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
              <span>Health <strong>{w.health_score ?? '—'}</strong></span>
              <span style={{ color: w.sybil_risk_score > 60 ? '#ef4444' : w.sybil_risk_score > 30 ? '#f59e0b' : 'var(--signal)' }}>
                Sybil {w.sybil_risk_score ?? 0}
              </span>
            </div>
          </div>
        ))}
      </div>

      <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 12 }}>⚠️ Correlated Wallet Pairs</div>
      {pairs.length === 0
        ? <div style={{ ...card, color: 'var(--text-secondary)', fontSize: 13 }}>No suspicious correlations detected (score &lt; 20).</div>
        : pairs.map((p, i) => (
          <div key={i} style={{ ...card, borderLeft: `3px solid ${riskColor(p.risk_level)}` }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <span style={{ fontWeight: 600, fontSize: 13 }}>{addr(p.wallet_a)} ↔ {addr(p.wallet_b)}</span>
              <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: riskColor(p.risk_level) }}>{p.correlation_score}%</span>
                <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 99, background: riskColor(p.risk_level), color: '#fff', textTransform: 'uppercase', fontWeight: 700 }}>{p.risk_level}</span>
              </div>
            </div>
            {(p.evidence || []).map((e, j) => (
              <div key={j} style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 3 }}>• [{e.dimension}] {e.finding}</div>
            ))}
            {p.recommendation && <div style={{ fontSize: 12, marginTop: 6, color: 'var(--text)' }}>💡 {p.recommendation}</div>}
          </div>
        ))
      }
    </div>
  )
}
