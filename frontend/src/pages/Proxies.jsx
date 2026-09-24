import React from 'react'
import { Card } from '../components/ui'

export default function Proxies() {
  return (
    <Card title="Proxy management">
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14 }}>
        <div style={{
          width: 36, height: 36, borderRadius: 10, flexShrink: 0,
          background: 'var(--signal-dim)', color: 'var(--signal)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16,
        }}>
          ⇄
        </div>
        <div>
          <p style={{ margin: 0, fontSize: 13.5, color: 'var(--text)' }}>
            Proxy support is ready on the backend.
          </p>
          <p style={{ margin: '8px 0 0', fontSize: 12.5, color: 'var(--text-faint)' }}>
            Configure proxies via the API — a dedicated UI for managing them here is coming soon.
          </p>
        </div>
      </div>
    </Card>
  )
}
