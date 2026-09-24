import React, { useEffect, useState } from 'react'
import api from '../api'
import { Card, Badge, EmptyState, SkeletonRows } from '../components/ui'

export default function Tasks() {
  const [projects, setProjects] = useState([])
  const [selectedProj, setSelectedProj] = useState(null)
  const [tasks, setTasks] = useState([])
  const [loadingTasks, setLoadingTasks] = useState(false)

  useEffect(() => { api.get('/projects/').then(r => setProjects(r.data)) }, [])

  const loadTasks = async (projId) => {
    if (!projId) { setSelectedProj(null); return }
    setSelectedProj(projId)
    setLoadingTasks(true)
    try {
      const res = await api.get(`/projects/${projId}/tasks`)
      setTasks(res.data)
    } finally {
      setLoadingTasks(false)
    }
  }

  const selectedName = projects.find(p => String(p.id) === String(selectedProj))?.name

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <Card title="Task configurations">
        <p style={{ fontSize: 12.5, color: 'var(--text-dim)', marginTop: -8, marginBottom: 14 }}>
          Choose a project to view how its on-chain tasks are configured.
        </p>
        <select onChange={e => loadTasks(e.target.value)} defaultValue="" style={{ minWidth: 240 }}>
          <option value="">Select a project…</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </Card>

      {selectedProj && (
        <Card title={`Tasks · ${selectedName || `Project ${selectedProj}`}`}>
          <div className="table-scroll"><table>
            <thead>
              <tr>
                <th>ID</th><th>Type</th><th>Min / Max</th><th>Daily TX</th><th>Bidirectional</th><th>Enabled</th>
              </tr>
            </thead>
            <tbody>
              {loadingTasks && <SkeletonRows rows={3} cols={6} />}
              {!loadingTasks && tasks.map(t => (
                <tr key={t.id}>
                  <td className="mono" style={{ color: 'var(--text-dim)' }}>{t.id}</td>
                  <td>{t.task_type}</td>
                  <td className="mono">{t.min_amount} – {t.max_amount}</td>
                  <td className="mono">{t.daily_tx_min}–{t.daily_tx_max}</td>
                  <td><Badge status={t.bidirectional}>{t.bidirectional ? 'Yes' : 'No'}</Badge></td>
                  <td><Badge status={t.enabled}>{t.enabled ? 'Enabled' : 'Disabled'}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table></div>
          {!loadingTasks && tasks.length === 0 && (
            <EmptyState icon="☐" title="No tasks configured" hint="This project has no task configurations yet." />
          )}
        </Card>
      )}
    </div>
  )
}
