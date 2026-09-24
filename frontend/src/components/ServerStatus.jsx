import React, { useEffect, useState } from 'react'
import api from '../api'
import { Card } from './ui'

function Meter({ label, percent, sub }) {
  const tone = percent > 85 ? 'var(--rose)' : percent > 65 ? 'var(--amber)' : 'var(--signal)'
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5 }}>
        <span style={{ color: 'var(--text-dim)' }}>{label}</span>
        <span className="mono" style={{ color: 'var(--text)', fontWeight: 600 }}>{percent}%</span>
      </div>
      <div style={{ height: 6, borderRadius: 4, background: 'var(--bg-elevated)', overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${Math.min(percent, 100)}%`, background: tone, borderRadius: 4, transition: 'width 0.4s ease' }} />
      </div>
      {sub && <span style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>{sub}</span>}
    </div>
  )
}

export default function ServerStatus() {
  const [status, setStatus] = useState(null)
  const [err, setErr] = useState(false)

  useEffect(() => {
    api.get('/reports/server').then(r => setStatus(r.data)).catch(() => setErr(true))
  }, [])

  return (
    <Card title="Server health">
      {err && <p className="error">Could not reach server metrics.</p>}
      {!status && !err && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {[1, 2, 3].map(i => <div key={i} className="skeleton" style={{ height: 16 }} />)}
        </div>
      )}
      {status && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Meter label="RAM" percent={status.ram_percent} sub={`${status.ram_used_gb} / ${status.ram_total_gb} GB`} />
          <Meter label="CPU" percent={status.cpu_percent} />
          <Meter label="Disk" percent={status.disk_percent} sub={`${status.disk_free_gb} GB free`} />
        </div>
      )}
    </Card>
  )
}
