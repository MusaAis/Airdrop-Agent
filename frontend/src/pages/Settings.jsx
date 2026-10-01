import React from 'react'
import { Card } from '../components/ui'
import AutonomyPanel from '../components/AutonomyPanel'
import SystemPanel from '../components/SystemPanel'

export default function Settings() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <SystemPanel />
      <AutonomyPanel />

      <Card title="Environment">
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 10, flexShrink: 0,
            background: 'var(--violet-dim)', color: 'var(--violet)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16,
          }}>
            ⚙
          </div>
          <div>
            <p style={{ margin: 0, fontSize: 13.5, color: 'var(--text)' }}>
              Environment variables are controlled via <code className="mono" style={{ background: 'var(--bg-elevated)', padding: '2px 6px', borderRadius: 4 }}>.env</code> on the server.
            </p>
            <p style={{ margin: '8px 0 0', fontSize: 12.5, color: 'var(--text-faint)' }}>
              Other in-app settings aren't available yet — update values directly on the host and restart the agent for changes to take effect.
            </p>
          </div>
        </div>
      </Card>
    </div>
  )
}
