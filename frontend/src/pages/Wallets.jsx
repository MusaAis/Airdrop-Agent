import React, { useEffect, useState } from 'react'
import api from '../api'
import Spinner from '../components/Spinner'
import { Card, Badge, EmptyState, SkeletonRows } from '../components/ui'

function truncate(addr) {
  if (!addr || addr.length < 12) return addr
  return `${addr.slice(0, 6)}…${addr.slice(-4)}`
}

export default function Wallets({ token }) {
  const [wallets, setWallets] = useState([])
  const [count, setCount] = useState(1)
  const [privKey, setPrivKey] = useState('')
  const [importWarning, setImportWarning] = useState(false)
  const [loading, setLoading] = useState(false)
  const [initialLoad, setInitialLoad] = useState(true)
  const [actionMessage, setActionMessage] = useState('')
  const [copiedId, setCopiedId] = useState(null)

  const fetchWallets = async () => {
    setLoading(true)
    try {
      const r = await api.get('/wallets/')
      setWallets(r.data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
      setInitialLoad(false)
    }
  }

  useEffect(() => { fetchWallets() }, [])

  const generate = async () => {
    setActionMessage('')
    setLoading(true)
    try {
      await api.post('/wallets/generate', { count, start_index: wallets.length })
      fetchWallets()
    } catch (e) {
      setActionMessage('Error generating wallets')
    } finally {
      setLoading(false)
    }
  }

  const importWallet = async () => {
    if (!privKey) return alert('Private key required')
    if (!importWarning) {
      setImportWarning(true)
      return
    }
    setActionMessage('')
    setLoading(true)
    try {
      await api.post('/wallets/import', { private_key: privKey, tags: [] })
      setPrivKey('')
      setImportWarning(false)
      fetchWallets()
    } catch (e) {
      setActionMessage('Error importing wallet')
    } finally {
      setLoading(false)
    }
  }

  const toggleStatus = async (id, status) => {
    setActionMessage('')
    setLoading(true)
    try {
      await api.put(`/wallets/${id}/status?status=${status}`)
      fetchWallets()
    } catch (e) {
      setActionMessage('Error updating wallet')
    } finally {
      setLoading(false)
    }
  }

  const copyAddress = (addr, id) => {
    navigator.clipboard?.writeText(addr)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 1200)
  }

  const activeCount = wallets.filter(w => w.status === 'active').length

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
          <span className="mono" style={{ fontSize: 22, fontWeight: 600 }}>{wallets.length}</span>
          <span style={{ fontSize: 13, color: 'var(--text-dim)' }}>total wallets</span>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
          <span className="mono" style={{ fontSize: 22, fontWeight: 600, color: 'var(--signal)' }}>{activeCount}</span>
          <span style={{ fontSize: 13, color: 'var(--text-dim)' }}>active</span>
        </div>
      </div>

      <div className="grid">
        <Card title="Generate HD wallets">
          <p style={{ fontSize: 12.5, color: 'var(--text-dim)', marginTop: -8, marginBottom: 14 }}>
            Derives new wallets from your configured seed phrase. Safe and recommended.
          </p>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <input type="number" value={count} onChange={e => setCount(Number(e.target.value))} min={1} />
            <button className="primary" onClick={generate} disabled={loading}>Generate</button>
          </div>
        </Card>

        <Card title="Import private key">
          <p style={{ fontSize: 12.5, color: 'var(--text-dim)', marginTop: -8, marginBottom: 14 }}>
            Only do this on a server you fully trust.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <input
              type="text"
              placeholder="0x… private key"
              value={privKey}
              onChange={e => setPrivKey(e.target.value)}
              style={{ width: '100%' }}
            />
            {importWarning && (
              <div className="error">
                ⚠ You're about to send a raw private key over the network. Only continue if you fully trust this server — HD wallets are safer.
              </div>
            )}
            <button className={importWarning ? 'danger' : ''} onClick={importWallet} disabled={loading} style={{ alignSelf: 'flex-start' }}>
              {importWarning ? 'Confirm import' : 'Import private key'}
            </button>
          </div>
        </Card>
      </div>

      {loading && !initialLoad && <Spinner inline label="Working…" />}
      {actionMessage && <p className="error">{actionMessage}</p>}

      <Card title="All wallets">
        <div className="table-scroll"><table>
          <thead>
            <tr><th>ID</th><th>Address</th><th>Status</th><th style={{ textAlign: 'right' }}>Actions</th></tr>
          </thead>
          <tbody>
            {initialLoad && <SkeletonRows rows={4} cols={4} />}
            {!initialLoad && wallets.map(w => (
              <tr key={w.id}>
                <td className="mono" style={{ color: 'var(--text-dim)' }}>{w.id}</td>
                <td>
                  <button
                    className="ghost sm mono"
                    onClick={() => copyAddress(w.address, w.id)}
                    style={{ padding: '4px 8px', fontSize: 12.5 }}
                    title={w.address}
                  >
                    {copiedId === w.id ? 'Copied ✓' : truncate(w.address)}
                  </button>
                </td>
                <td><Badge status={w.status}>{w.status}</Badge></td>
                <td>
                  <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                    {w.status !== 'active' && <button className="sm" onClick={() => toggleStatus(w.id, 'active')}>Activate</button>}
                    {w.status !== 'paused' && <button className="sm" onClick={() => toggleStatus(w.id, 'paused')}>Pause</button>}
                    <button className="sm danger" onClick={() => toggleStatus(w.id, 'archived')}>Archive</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table></div>
        {!initialLoad && wallets.length === 0 && (
          <EmptyState icon="◇" title="No wallets yet" hint="Generate HD wallets or import a private key to get started." />
        )}
      </Card>
    </div>
  )
}
