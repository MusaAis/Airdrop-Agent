import React, { useEffect, useState } from 'react'
import api from '../api'
import { Card, EmptyState } from './ui'

export default function WorkerSlotView() {
  const [slots, setSlots] = useState([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    const load = () => api.get('/agent/workers').then(r => { setSlots(r.data); setLoaded(true) }).catch(() => setLoaded(true))
    load()
    const interval = setInterval(load, 5000)
    return () => clearInterval(interval)
  }, [])

  return (
    <Card title="Worker slots" action={<span style={{ fontSize: 12, color: 'var(--text-faint)' }}>refreshes every 5s</span>}>
      {!loaded && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 10 }}>
          {Array.from({ length: 4 }).map((_, i) => <div key={i} className="skeleton" style={{ height: 56, borderRadius: 10 }} />)}
        </div>
      )}
      {loaded && slots.length === 0 && (
        <EmptyState icon="⏸" title="No worker slots reported" hint="The agent may be idle or unreachable." />
      )}
      {loaded && slots.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(170px, 1fr))', gap: 10 }}>
          {slots.map((s, i) => {
            const busy = s.status !== 'idle'
            return (
              <div
                key={i}
                style={{
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-md)',
                  padding: '12px 14px',
                  background: busy ? 'var(--signal-dim)' : 'var(--bg-elevated)',
                  borderColor: busy ? 'rgba(94,234,212,0.3)' : 'var(--border)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 4,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-faint)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: busy ? 'var(--signal)' : 'var(--text-faint)' }} />
                  Slot {i}
                </div>
                {busy ? (
                  <>
                    <span className="mono" style={{ fontSize: 12.5, fontWeight: 600 }}>{s.wallet_id}</span>
                    <span style={{ fontSize: 12, color: 'var(--text-dim)' }}>{s.project} · {s.task_type}</span>
                  </>
                ) : (
                  <span style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>Idle</span>
                )}
              </div>
            )
          })}
        </div>
      )}
    </Card>
  )
}
