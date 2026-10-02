import React, { useMemo, useState } from 'react'
import api from '../api'
import useApi from '../hooks/useApi'
import { Card, PageHeader, StatTile, EmptyState, SkeletonBlock, Badge, Segmented, Meter } from '../components/ui'
import { shortAddr } from '../lib/format'

const TONE = { critical: 'danger', high: 'danger', medium: 'warning', low: 'success' }
const riskTone = n => (n > 60 ? 'var(--rose)' : n > 30 ? 'var(--amber)' : 'var(--signal)')

export default function Sybil() {
  const { data, loading, error, reload, refreshing } = useApi(async () => {
    const [s, w] = await Promise.all([api.get('/reports/sybil'), api.get('/wallets/')])
    const pairs = Array.isArray(s.data) ? s.data : (s.data?.suspicious_pairs || [])
    return { pairs, wallets: Array.isArray(w.data) ? w.data : [] }
  }, [])
  const [sort, setSort] = useState('risk')

  const pairs = data?.pairs || []
  const wallets = data?.wallets || []
  const addr = id => { const w = wallets.find(x => x.id === id); return w ? `#${w.id} ${shortAddr(w.address)}` : `#${id}` }

  const sorted = useMemo(() => {
    const w = [...wallets]
    if (sort === 'risk') w.sort((a, b) => (b.sybil_risk_score ?? 0) - (a.sybil_risk_score ?? 0))
    else if (sort === 'health') w.sort((a, b) => (a.health_score ?? 100) - (b.health_score ?? 100))
    else w.sort((a, b) => a.id - b.id)
    return w
  }, [wallets, sort])

  const flagged = wallets.filter(w => (w.sybil_risk_score ?? 0) > 30).length
  const avgHealth = wallets.length ? Math.round(wallets.reduce((s, w) => s + (w.health_score ?? 100), 0) / wallets.length) : null

  return (
    <div className="stack">
      <PageHeader
        title="Sybil risk"
        subtitle="How correlated your wallets look to an airdrop's anti-sybil filter, plus each wallet's health."
        actions={<button onClick={reload} disabled={refreshing}>{refreshing ? 'Refreshing…' : 'Refresh'}</button>}
      />
      {error && <div className="error">{error}</div>}

      <div className="grid-stats">
        <Card><StatTile label="Wallets" value={loading ? '…' : wallets.length} /></Card>
        <Card><StatTile label="Avg health" value={loading ? '…' : avgHealth ?? '—'} tone="signal" /></Card>
        <Card><StatTile label="Elevated risk" value={loading ? '…' : flagged} tone={flagged ? 'amber' : 'default'} sub="score above 30" /></Card>
        <Card><StatTile label="Correlated pairs" value={loading ? '…' : pairs.length} tone={pairs.length ? 'rose' : 'default'} /></Card>
      </div>

      <Card
        title="Wallet health"
        action={<Segmented value={sort} onChange={setSort} options={[{ value: 'risk', label: 'Riskiest' }, { value: 'health', label: 'Lowest health' }, { value: 'id', label: 'By id' }]} />}
      >
        {loading ? <SkeletonBlock height={90} /> : sorted.length === 0 ? (
          <EmptyState icon="◇" title="No wallets yet" hint="Generate or import wallets first." />
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 10 }}>
            {sorted.map(w => (
              <div key={w.id} className="card flat tight stack-sm" style={{ gap: 10 }}>
                <div className="row-between">
                  <span className="mono" style={{ fontSize: 12.5 }}>#{w.id} · {shortAddr(w.address)}</span>
                  <Badge status={w.status}>{w.status}</Badge>
                </div>
                <Meter label="Health" percent={w.health_score ?? 100} tone="var(--signal)" />
                <Meter label="Sybil risk" percent={w.sybil_risk_score ?? 0} tone={riskTone(w.sybil_risk_score ?? 0)} />
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card title="Correlated wallet pairs">
        {loading ? <SkeletonBlock /> : pairs.length === 0 ? (
          <EmptyState icon="✓" title="No suspicious correlations" hint="No pair scored 20 or higher." />
        ) : (
          <div className="stack-sm">
            {pairs.map((p, i) => (
              <div key={i} className="card flat tight" style={{ borderLeft: `3px solid ${p.risk_level === 'low' ? 'var(--signal)' : p.risk_level === 'medium' ? 'var(--amber)' : 'var(--rose)'}` }}>
                <div className="row-between" style={{ marginBottom: 8 }}>
                  <span style={{ fontWeight: 600, fontSize: 13 }}>{addr(p.wallet_a)} ↔ {addr(p.wallet_b)}</span>
                  <span className="row" style={{ gap: 8 }}>
                    <span className="mono" style={{ fontWeight: 700 }}>{p.correlation_score}%</span>
                    <Badge tone={TONE[p.risk_level] || 'neutral'}>{p.risk_level}</Badge>
                  </span>
                </div>
                {(p.evidence || []).map((e, j) => (
                  <div key={j} className="muted" style={{ fontSize: 12.5, marginBottom: 3 }}>• <span className="faint">[{e.dimension}]</span> {e.finding}</div>
                ))}
                {p.recommendation && <div style={{ fontSize: 12.5, marginTop: 8 }}>💡 {p.recommendation}</div>}
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
