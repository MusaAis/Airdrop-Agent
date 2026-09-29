import React, { useState } from 'react'
import api from '../api'
import Spinner from '../components/Spinner'
import { Card, EmptyState, Badge } from '../components/ui'

const REPORT_TYPES = [
  { key: 'summary', label: 'AI Summary' },
  { key: 'eligibility', label: 'Eligibility' },
  { key: 'gas-spend', label: 'Gas spend' },
  { key: 'daily-progress', label: 'Daily progress' },
  { key: 'gas', label: 'Gas by chain' },
  { key: 'sybil', label: 'Sybil risk' },
  { key: 'activity', label: 'Activity' },
  { key: 'server', label: 'Server' },
]

function SummaryView({ data }) {
  if (!data) return null
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <Badge status={data.ai_generated ? 'active' : 'pending'}>
          {data.ai_generated ? 'AI-narrated' : 'Plain summary (AI unavailable)'}
        </Badge>
        {data.facts?.window_hours && (
          <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>last {data.facts.window_hours}h</span>
        )}
      </div>
      <div style={{
        background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)',
        padding: 16, fontSize: 13.5, lineHeight: 1.7, whiteSpace: 'pre-wrap',
      }}>
        {data.narrative}
      </div>
      {data.facts?.trend_flags?.length > 0 && (
        <div>
          <div style={{ fontSize: 11, color: 'var(--text-faint)', textTransform: 'uppercase', marginBottom: 6 }}>Trend flags</div>
          {data.facts.trend_flags.map((f, i) => (
            <div key={i} className="error" style={{ marginBottom: 6 }}>{f}</div>
          ))}
        </div>
      )}
      <details>
        <summary style={{ fontSize: 12, color: 'var(--text-dim)', cursor: 'pointer' }}>Raw fact pack (what the AI was shown)</summary>
        <pre className="mono" style={{ fontSize: 11.5, marginTop: 10, whiteSpace: 'pre-wrap', color: 'var(--text-dim)' }}>
          {JSON.stringify(data.facts, null, 2)}
        </pre>
      </details>
      {data.error && <div className="error">{data.error}</div>}
    </div>
  )
}

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
      if (projectId && endpoint !== 'server' && endpoint !== 'sybil' && endpoint !== 'summary') url += `?project_id=${projectId}`
      const res = await api.get(url)
      setData(res.data)
    } catch (e) {
      setData(null)
    } finally {
      setLoading(false)
    }
  }

  const activeLabel = activeTab ? REPORT_TYPES.find(r => r.key === activeTab)?.label : 'Output'

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

      <Card title={activeLabel}>
        {loading && <Spinner inline label={activeTab === 'summary' ? 'Generating AI summary…' : 'Fetching report…'} />}
        {!loading && !activeTab && (
          <EmptyState icon="▤" title="Choose a report" hint="Select a report type above to view its data." />
        )}
        {!loading && activeTab && data == null && (
          <EmptyState icon="!" title="Couldn't load report" hint="The endpoint may have returned an error." />
        )}
        {!loading && data != null && activeTab === 'summary' && <SummaryView data={data} />}
        {!loading && data != null && activeTab !== 'summary' && (
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
