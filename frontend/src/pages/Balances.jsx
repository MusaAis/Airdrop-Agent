import React, { useMemo, useState } from 'react'
import api from '../api'
import useApi, { apiError } from '../hooks/useApi'
import { useToast } from '../components/Toast'
import { Card, Badge, PageHeader, EmptyState, DataTable, StatTile, Segmented } from '../components/ui'
import { shortAddr, fmtUsd, fmtDateTime } from '../lib/format'

function fmtBalance(v) {
  if (v === null || v === undefined) return '—'
  if (v === 0) return '0'
  if (v < 0.0001) return v.toExponential(2)
  return v.toFixed(v < 1 ? 6 : 4)
}

const latest = s => s.balances.reduce((l, b) => (!l || (b.last_updated && b.last_updated > l) ? b.last_updated : l), null)

export default function Balances() {
  const toast = useToast()
  const { data, loading, error, reload } = useApi(() => api.get('/wallets/balances/all').then(r => r.data), [])
  const summaries = Array.isArray(data) ? data : []

  const [filter, setFilter] = useState('all')
  const [expanded, setExpanded] = useState(null)
  const [refreshingAll, setRefreshingAll] = useState(false)
  const [refreshingId, setRefreshingId] = useState(null)

  const refreshAll = async () => {
    setRefreshingAll(true)
    try {
      const r = await api.post('/wallets/balances/refresh-all', null, { timeout: 180000 })
      toast.success(r.data.message || 'Balances refreshed.')
      await reload()
    } catch (e) {
      toast.error(apiError(e, 'Refresh failed — with many wallets this can time out; refresh single wallets instead.'))
    } finally { setRefreshingAll(false) }
  }
  const refreshOne = async id => {
    setRefreshingId(id)
    try { await api.post(`/wallets/${id}/balances/refresh`); await reload() }
    catch (e) { toast.error(apiError(e, `Could not refresh wallet ${id}.`)) }
    finally { setRefreshingId(null) }
  }

  const totals = useMemo(() => {
    const funded = summaries.filter(s => (s.total_usd || 0) > 0).length
    return {
      usd: summaries.reduce((sum, s) => sum + (s.total_usd || 0), 0),
      funded, empty: summaries.length - funded, gas: summaries.filter(s => s.is_gas_wallet).length,
    }
  }, [summaries])

  const visible = summaries.filter(s =>
    filter === 'funded' ? (s.total_usd || 0) > 0 : filter === 'empty' ? (s.total_usd || 0) === 0 : true)

  const columns = [
    {
      key: 'wallet', label: 'Wallet',
      render: s => (<span className="row" style={{ gap: 6, justifyContent: 'flex-end' }}><span className="mono">{shortAddr(s.address)}</span>{s.is_gas_wallet && <Badge tone="warning">gas</Badge>}</span>),
    },
    { key: 'status', label: 'Status', render: s => <Badge status={s.status}>{s.status}</Badge> },
    { key: 'usd', label: 'Total USD', num: true, render: s => <span className="mono" style={{ fontWeight: 600, color: (s.total_usd || 0) > 0 ? 'var(--signal)' : 'var(--text-faint)' }}>{fmtUsd(s.total_usd)}</span> },
    { key: 'tokens', label: 'Tokens', render: s => <span className="muted" style={{ fontSize: 12 }}>{s.balances.length ? `${s.balances.length} token(s) ${expanded === s.wallet_id ? '▲' : '▼'}` : 'no data yet'}</span> },
    { key: 'updated', label: 'Updated', render: s => <span className="faint" style={{ fontSize: 12 }}>{latest(s) ? fmtDateTime(latest(s)) : '—'}</span> },
    { key: 'act', label: '', actions: true, render: s => <button className="ghost sm" onClick={() => refreshOne(s.wallet_id)} disabled={refreshingId === s.wallet_id}>{refreshingId === s.wallet_id ? 'Refreshing…' : 'Refresh'}</button> },
  ]

  return (
    <div className="stack">
      <PageHeader title="Balances" subtitle="Last known balances per wallet. “Refresh all” reads every wallet on-chain." />

      <div className="grid-stats">
        <Card><StatTile label="Total USD" value={loading ? '…' : fmtUsd(totals.usd)} tone="signal" /></Card>
        <Card><StatTile label="Funded" value={loading ? '…' : totals.funded} /></Card>
        <Card><StatTile label="Empty" value={loading ? '…' : totals.empty} tone="rose" /></Card>
        <Card><StatTile label="Gas wallets" value={loading ? '…' : totals.gas} tone="amber" /></Card>
      </div>

      <Card
        title="Wallet balances"
        action={
          <div className="row">
            <Segmented value={filter} onChange={setFilter} options={['all', 'funded', 'empty']} />
            <button className="sm" onClick={refreshAll} disabled={refreshingAll}>{refreshingAll ? 'Reading chains…' : 'Refresh all (on-chain)'}</button>
          </div>
        }
      >
        {error && <div className="error" style={{ marginBottom: 12 }}>{error}</div>}
        <DataTable
          columns={columns} rows={visible} loading={loading} skeletonRows={5} rowKey="wallet_id"
          onRowClick={s => s.balances.length && setExpanded(e => (e === s.wallet_id ? null : s.wallet_id))}
          expanded={expanded}
          renderExpanded={s => (
            <div className="stack-sm" style={{ padding: '6px 4px' }}>
              {s.balances.map((b, i) => (
                <div key={i} className="row-between" style={{ fontSize: 12.5 }}>
                  <span className="muted">chain #{b.chain_id} · {b.token_symbol}</span>
                  <span className="mono">{fmtBalance(b.balance)} {b.token_symbol} <span className="faint">· {fmtUsd(b.usd_value)}</span></span>
                </div>
              ))}
            </div>
          )}
          empty={<EmptyState icon="◇" title={summaries.length ? 'No wallets in this view' : 'No wallets yet'} hint={summaries.length ? 'Try another filter.' : 'Generate or import a wallet first, then refresh balances.'} />}
        />
      </Card>
    </div>
  )
}
