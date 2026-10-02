import React, { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../api'
import useApi from '../hooks/useApi'
import { useToast } from '../components/Toast'
import { Card, PageHeader, StatTile, EmptyState, SkeletonBlock, Badge, DataTable, Icon } from '../components/ui'
import { fmtUsd, shortAddr } from '../lib/format'
import { apiError } from '../hooks/useApi'

// Read-only on purpose: the panel finds what is claimable, it never sends a claim.
// Claiming spends real gas and can't be undone, and auto-claim was removed deliberately
// (PLAN.md §3). A manual claim with a confirm step + dry-run is under "Known, not built".
export default function Claims() {
  const toast = useToast()
  const [scanning, setScanning] = useState(false)
  const scan = useApi(() => api.get('/claims/scan').then(r => r.data), [])
  const contracts = useApi(() => api.get('/ops/claims/contracts').then(r => r.data), [])

  const data = scan.data
  const watched = Array.isArray(contracts.data) ? contracts.data : []
  const items = data?.items || []

  const rescan = async () => {
    setScanning(true)
    try {
      const r = await api.get('/claims/scan', { params: { refresh: true }, timeout: 180000 })
      scan.setData(r.data)
      toast.success(r.data.count ? `Found ${r.data.count} claimable position(s).` : 'Scan finished — nothing claimable.')
    } catch (e) {
      toast.error(apiError(e, 'Scan failed.'))
    } finally { setScanning(false) }
  }

  const copy = (text, label) => { navigator.clipboard?.writeText(text); toast.info(`${label} copied`) }

  const byProject = useMemo(() => {
    const m = new Map()
    for (const it of items) {
      if (!m.has(it.project_id)) m.set(it.project_id, { name: it.project_name, rows: [] })
      m.get(it.project_id).rows.push(it)
    }
    return [...m.entries()]
  }, [items])
  const wallets = new Set(items.map(i => i.wallet_id)).size
  const noContracts = !contracts.loading && watched.length === 0

  const contractCols = [
    { key: 'project', label: 'Project', render: c => <Link to={`/projects/${c.project_id}`}>{c.project}</Link> },
    { key: 'label', label: 'Label', render: c => <Badge tone="neutral">{c.label}</Badge> },
    { key: 'chain', label: 'Chain' },
    { key: 'address', label: 'Address', render: c => <span className="mono" style={{ fontSize: 12, overflowWrap: 'anywhere' }}>{c.address}</span> },
  ]

  return (
    <div className="stack">
      <PageHeader
        title="Claims"
        subtitle="Scans each project's claim contracts for balances your active wallets can claim. Read-only — claiming is done by hand."
        actions={
          <button className="primary" onClick={rescan} disabled={scanning || noContracts}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
              <span style={{ display: 'flex', animation: scanning ? 'spin .8s linear infinite' : 'none' }}><Icon name="refresh" size={15} /></span>
              {scanning ? 'Scanning chains…' : 'Rescan now'}
            </span>
          </button>
        }
      />

      {(scan.error || data?.error) && <div className="error">{scan.error || data.error}</div>}

      <div className="grid-stats">
        <Card><StatTile label="Claimable positions" value={scan.loading ? '…' : items.length} tone={items.length ? 'signal' : 'default'} /></Card>
        <Card><StatTile label="Est. value" value={scan.loading ? '…' : fmtUsd(data?.total_usd_estimate)} tone="signal" sub="gas-token price × amount" /></Card>
        <Card><StatTile label="Wallets" value={scan.loading ? '…' : wallets} tone="violet" /></Card>
        <Card><StatTile label="Watched contracts" value={contracts.loading ? '…' : watched.length} sub={data?.scanned_at ? `last scan ${new Date(data.scanned_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}${data.cached ? ' (cached)' : ''}` : undefined} /></Card>
      </div>

      {scan.loading ? <SkeletonBlock height={120} /> : byProject.length === 0 ? (
        <Card>
          <EmptyState
            icon="◌" title="Nothing claimable right now"
            hint={noContracts ? 'No claim contracts are watched yet — add one on a project (label containing “claim”), then rescan.' : 'No wallet reported a claimable balance on the watched contracts.'}
          />
        </Card>
      ) : (
        byProject.map(([pid, g]) => (
          <Card key={pid} title={g.name} action={<Badge tone="success">{g.rows.length} position{g.rows.length > 1 ? 's' : ''}</Badge>}>
            <div className="stack-sm">
              {g.rows.map((r, i) => (
                <div key={i} className="card flat tight" style={{ display: 'flex', gap: 12, justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap' }}>
                  <div style={{ minWidth: 0 }}>
                    <div className="mono" style={{ fontWeight: 600 }}>
                      {r.human_amount} {r.token_symbol} <span className="muted" style={{ fontWeight: 400 }}>≈ {fmtUsd(r.usd_estimate)}</span>
                    </div>
                    <div className="faint" style={{ fontSize: 12, marginTop: 2 }}>Wallet #{r.wallet_id} · {shortAddr(r.wallet_address)} · {r.chain_name}</div>
                  </div>
                  <div className="row">
                    <button className="sm" onClick={() => copy(r.wallet_address, 'Wallet address')}>Copy wallet</button>
                    <button className="sm" onClick={() => copy(r.contract_address, 'Claim contract')}>Copy contract</button>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        ))
      )}

      <Card title="Watched claim contracts">
        <DataTable
          columns={contractCols} rows={watched} loading={contracts.loading} skeletonRows={2}
          empty={<EmptyState icon="◫" title="No claim contracts yet" hint="Open a project and add a contract whose label contains the word “claim”." />}
        />
      </Card>

      <div className="notice">
        Estimates assume 18 decimals and are priced with the chain's gas-token price, so treat them as a hint, not a quote.
        Always confirm the real amount on the project's own claim page before claiming.
      </div>
    </div>
  )
}
