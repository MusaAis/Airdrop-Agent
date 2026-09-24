import React, { useState } from 'react'
import api from '../api'
import Spinner from '../components/Spinner'
import { Card, EmptyState } from '../components/ui'

const REPORT_TYPES = [
  { key: 'eligibility', label: 'Eligibility' },
  { key: 'roi', label: 'ROI' },
  { key: 'daily-progress', label: 'Daily progress' },
  { key: 'gas', label: 'Gas spend' },
  { key: 'sybil', label: 'Sybil risk' },
  { key: 'activity', label: 'Activity' },
  { key: 'server', label: 'Server' },
]

export default function Reports() {
  const [activeTab, setActiveTab] = useState(null)
  const [data, setData] = useState(null)
  const [projectId, setProjectId] = useState('')
  const [loading, setLoading] = useState(false)

  const fetchReport = async (endpoint) => {
    setLoading(true)
    setActiveTab(endpoint)
    try {
      let url = `/reports/${endpoint}`
      if (projectId && endpoint !== 'server' && endpoint !== 'sybil') url += `?project_id=${projectId}`
      const res = await api.get(url)
      setData(res.data)
    } catch (e) {
      setData(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <Card title="Reports">
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
          <input
            placeholder="Project ID (optional)"
            value={projectId}
            onChange={e => setProjectId(e.target.value)}
            style={{ width: 180 }}
          />
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {REPORT_TYPES.map(r => (
            <button
              key={r.key}
              onClick={() => fetchReport(r.key)}
              className={activeTab === r.key ? 'primary' : ''}
              style={{ fontSize: 12.5 }}
            >
              {r.label}
            </button>
          ))}
        </div>
      </Card>

      <Card title={activeTab ? REPORT_TYPES.find(r => r.key === activeTab)?.label : 'Output'}>
        {loading && <Spinner inline label="Fetching report…" />}
        {!loading && !activeTab && (
          <EmptyState icon="▤" title="Choose a report" hint="Select a report type above to view its data." />
        )}
        {!loading && activeTab && data == null && (
          <EmptyState icon="!" title="Couldn't load report" hint="The endpoint may have returned an error." />
        )}
        {!loading && data != null && (
          <pre
            className="mono"
            style={{
              background: 'var(--bg-elevated)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              padding: 16,
              fontSize: 12.5,
              overflowX: 'auto',
              color: 'var(--text-dim)',
              margin: 0,
            }}
          >
            {JSON.stringify(data, null, 2)}
          </pre>
        )}
      </Card>
    </div>
  )
}
