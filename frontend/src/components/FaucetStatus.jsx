import React, { useEffect, useState } from 'react'
import api from '../api'
import { Badge, DataTable, SkeletonBlock } from './ui'

// Per-wallet faucet cooldown view, backed by GET /faucets/status/{wallet_id}
// (the route existed but nothing in the UI used it).
export default function FaucetStatus({ walletId, chains, refreshKey }) {
  const [rows, setRows] = useState(null)
  useEffect(() => {
    if (!walletId) { setRows(null); return }
    setRows(null)
    api.get(`/faucets/status/${walletId}`).then(r => setRows(r.data)).catch(() => setRows([]))
  }, [walletId, refreshKey])

  if (!walletId) return null
  if (rows === null) return <div style={{ marginTop: 14 }}><SkeletonBlock height={40} /></div>
  if (rows.length === 0) return <p className="hint faint" style={{ marginTop: 14 }}>No enabled faucets.</p>

  const chain = id => chains.find(c => c.id === id)?.name || (id ? `#${id}` : 'any')
  const cols = [
    { key: 'faucet_name', label: 'Faucet' },
    { key: 'chain', label: 'Chain', render: r => chain(r.chain_id) },
    { key: 'claim', label: 'Claimable', render: r => (r.claimable_now ? <Badge status="success">now</Badge> : <Badge status="pending">in {r.cooldown_remaining_hours}h</Badge>) },
    {
      key: 'last', label: 'Last request',
      render: r => <span className="muted" style={{ fontSize: 12 }}>{r.last_requested_at ? `${r.last_requested_at.slice(0, 16).replace('T', ' ')} · ${r.last_status}` : '—'}</span>,
    },
  ]
  return <div style={{ marginTop: 14 }}><DataTable columns={cols} rows={rows} rowKey="faucet_id" /></div>
}
