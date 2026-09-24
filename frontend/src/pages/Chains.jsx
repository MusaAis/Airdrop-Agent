import React, { useEffect, useState } from 'react'
import api from '../api'
import { Card, Badge, EmptyState } from '../components/ui'

export default function Chains() {
  const [chains, setChains] = useState([])
  const [loaded, setLoaded] = useState(false)
  const [newChain, setNewChain] = useState({ name: '', chain_id: '', rpc_urls: '', gas_token_symbol: 'ETH', gas_token_is_native: true })

  const fetchChains = () => api.get('/chains/').then(r => { setChains(r.data); setLoaded(true) }).catch(() => setLoaded(true))
  useEffect(() => { fetchChains() }, [])

  const add = async () => {
    if (!newChain.name || !newChain.chain_id) return
    const data = { ...newChain, rpc_urls: newChain.rpc_urls.split(',').map(s => s.trim()).filter(Boolean), chain_id: Number(newChain.chain_id) }
    await api.post('/chains/', data)
    setNewChain({ name: '', chain_id: '', rpc_urls: '', gas_token_symbol: 'ETH', gas_token_is_native: true })
    fetchChains()
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
      </Card>

      <Card title="Configured chains">
        {!loaded && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px,1fr))', gap: 10 }}>
            {Array.from({ length: 3 }).map((_, i) => <div key={i} className="skeleton" style={{ height: 70, borderRadius: 10 }} />)}
          </div>
        )}
        {loaded && chains.length === 0 && (
          <EmptyState icon="⛓" title="No chains configured" hint="Add a chain above to start routing tasks to it." />
        )}
        {loaded && chains.length > 0 && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px,1fr))', gap: 10 }}>
            {chains.map(c => (
              <div key={c.id} className="card" style={{ padding: 14, boxShadow: 'none' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>{c.name}</span>
                  <Badge status={c.enabled}>{c.enabled ? 'Enabled' : 'Disabled'}</Badge>
                </div>
                <div style={{ fontSize: 12.5, color: 'var(--text-dim)', display: 'flex', flexDirection: 'column', gap: 3 }}>
                  <span className="mono">Chain ID: {c.chain_id}</span>
                  <span>Gas token: {c.gas_token_symbol}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
