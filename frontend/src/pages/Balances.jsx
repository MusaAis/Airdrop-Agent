import React, { useEffect, useState } from 'react'
import api from '../api'
import Spinner from '../components/Spinner'
import { Card, Badge, EmptyState, SkeletonRows, StatTile } from '../components/ui'

function truncate(addr) {
  if (!addr || addr.length < 12) return addr
  return `${addr.slice(0, 6)}…${addr.slice(-4)}`
}

function fmtUsd(v) {
  if (v === null || v === undefined) return '—'
  return `$${v.toFixed(2)}`
}

function fmtBalance(v) {
  if (v === null || v === undefined) return '—'
  if (v === 0) return '0'
  if (v < 0.0001) return v.toExponential(2)
  return v.toFixed(v < 1 ? 6 : 4)
}

// NOTE: this page was not in the original master plan's frontend section —
// added because there was no way to see which wallets actually have funds
// without checking a chain explorer manually per wallet per chain. The
// backend wallet_balances table already existed but nothing read or wrote
// to it before this.
export default function Balances({ token }) {
  const [summaries, setSummaries] = useState([])
  const [loading, setLoading] = useState(false)
  const [initialLoad, setInitialLoad] = useState(true)
  const [refreshingAll, setRefreshingAll] = useState(false)
  const [refreshingWallet, setRefreshingWallet] = useState(null)
  const [actionMessage, setActionMessage] = useState('')
  const [filter, setFilter] = useState('all') // all / funded / empty
  const [expanded, setExpanded] = useState(null)

  const fetchBalances = async () => {
    setLoading(true)
    try {
      const r = await api.get('/wallets/balances/all')
      setSummaries(r.data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
      setInitialLoad(false)
    }
  }

  useEffect(() => { fetchBalances() }, [])

  const refreshAll = async () => {
    setActionMessage('')
    setRefreshingAll(true)
    try {
      const r = await api.post('/wallets/balances/refresh-all')
      setActionMessage(r.data.message || 'Refreshed.')
      await fetchBalances()
    } catch (e) {
      setActionMessage('Error refreshing balances — this can time out for large wallet sets, try refreshing individual wallets instead.')
    } finally {
      setRefreshingAll(false)
    }
  }

  const refreshOne = async (walletId) => {
    setRefreshingWallet(walletId)
    try {
      await api.post(`/wallets/${walletId}/balances/refresh`)
      await fetchBalances()
    } catch (e) {
      setActionMessage(`Error refreshing wallet ${walletId}`)
    } finally {
      setRefreshingWallet(null)
    }
  }

  const totalUsd = summaries.reduce((sum, s) => sum + (s.total_usd || 0), 0)
  const fundedCount = summaries.filter(s => (s.total_usd || 0) > 0).length
  const emptyCount = summaries.length - fundedCount
  const gasWalletCount = summaries.filter(s => s.is_gas_wallet).length

  const visible = summaries.filter(s => {
    if (filter === 'funded') return (s.total_usd || 0) > 0
    if (filter === 'empty') return (s.total_usd || 0) === 0
    return true
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 16 }}>
        <Card><StatTile label="Total USD" value={fmtUsd(totalUsd)} tone="signal" /></Card>
        <Card><StatTile label="Funded Wallets" value={fundedCount} tone="default" /></Card>
        <Card><StatTile label="Empty Wallets" value={emptyCount} tone="rose" /></Card>
        <Card><StatTile label="Gas Wallets" value={gasWalletCount} tone="amber" /></Card>
      </div>

      <Card
        title="Wallet Balances"
        action={
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <select value={filter} onChange={e => setFilter(e.target.value)} className="mono" style={{ fontSize: 13 }}>
              <option value="all">All wallets</option>
              <option value="funded">Funded only</option>
              <option value="empty">Empty only</option>
            </select>
            <button className="ghost sm" onClick={refreshAll} disabled={refreshingAll}>
              {refreshingAll ? <Spinner inline size={14} /> : 'Refresh All (on-chain)'}
            </button>
          </div>
        }
      >
        {actionMessage && <div style={{ fontSize: 13, color: 'var(--text-dim)', marginBottom: 12 }}>{actionMessage}</div>}

        {initialLoad ? (
          <div className="table-scroll"><table><tbody><SkeletonRows rows={5} cols={5} /></tbody></table></div>
        ) : summaries.length === 0 ? (
          <EmptyState icon="◇" title="No wallets yet" hint="Generate or import a wallet first, then refresh balances." />
        ) : (
          <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Wallet</th>
                <th>Status</th>
                <th>Total USD</th>
                <th>Tokens</th>
                <th>Last Updated</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {visible.map(s => {
                const isOpen = expanded === s.wallet_id
                const lastUpdated = s.balances.length
                  ? s.balances.reduce((latest, b) => (!latest || (b.last_updated && b.last_updated > latest)) ? b.last_updated : latest, null)
                  : null
                return (
                  <React.Fragment key={s.wallet_id}>
                    <tr style={{ cursor: s.balances.length ? 'pointer' : 'default' }} onClick={() => s.balances.length && setExpanded(isOpen ? null : s.wallet_id)}>
                      <td className="mono">
                        {truncate(s.address)}
                        {s.is_gas_wallet && <span style={{ marginLeft: 6 }}><Badge status="pending">gas</Badge></span>}
                      </td>
                      <td><Badge status={s.status}>{s.status}</Badge></td>
                      <td className="mono" style={{ fontWeight: 600, color: (s.total_usd || 0) > 0 ? 'var(--signal)' : 'var(--text-faint)' }}>
                        {fmtUsd(s.total_usd)}
                      </td>
                      <td style={{ fontSize: 12, color: 'var(--text-dim)' }}>
                        {s.balances.length ? `${s.balances.length} token(s) ${isOpen ? '▲' : '▼'}` : 'no data yet'}
                      </td>
                      <td style={{ fontSize: 12, color: 'var(--text-faint)' }}>
                        {lastUpdated ? new Date(lastUpdated).toLocaleString() : '—'}
                      </td>
                      <td onClick={e => e.stopPropagation()}>
                        <button className="ghost sm" onClick={() => refreshOne(s.wallet_id)} disabled={refreshingWallet === s.wallet_id}>
                          {refreshingWallet === s.wallet_id ? <Spinner inline size={12} /> : 'Refresh'}
                        </button>
                      </td>
                    </tr>
                    {isOpen && s.balances.map((b, i) => (
                      <tr key={i} style={{ background: 'var(--bg)' }}>
                        <td colSpan={2} style={{ paddingLeft: 32, fontSize: 12.5, color: 'var(--text-dim)' }}>
                          chain #{b.chain_id} · {b.token_symbol}
                        </td>
                        <td className="mono" style={{ fontSize: 12.5 }}>{fmtUsd(b.usd_value)}</td>
                        <td className="mono" style={{ fontSize: 12.5 }}>{fmtBalance(b.balance)} {b.token_symbol}</td>
                        <td colSpan={2} style={{ fontSize: 11, color: 'var(--text-faint)' }}>
                          {b.last_updated ? new Date(b.last_updated).toLocaleString() : ''}
                        </td>
                      </tr>
                    ))}
                  </React.Fragment>
                )
              })}
            </tbody>
          </table>
          </div>
        )}
      </Card>
    </div>
  )
}
