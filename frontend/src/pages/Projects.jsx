import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../api'
import { Card, Badge, EmptyState } from '../components/ui'

export default function Projects() {
  const [projects, setProjects] = useState([])
  const [loaded, setLoaded] = useState(false)
  const [newProj, setNewProj] = useState({ name: '', type: 'dapp', chain_ids: '' })

  const fetchProjects = () => api.get('/projects/').then(r => { setProjects(r.data); setLoaded(true) }).catch(() => setLoaded(true))
  useEffect(() => { fetchProjects() }, [])

  const add = async () => {
    if (!newProj.name) return
    await api.post('/projects/', { ...newProj, chain_ids: newProj.chain_ids.split(',').map(Number).filter(n => !Number.isNaN(n)) })
    setNewProj({ name: '', type: 'dapp', chain_ids: '' })
    fetchProjects()
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <Card
        title="Add project"
        action={
          <Link to="/projects/new" style={{ fontSize: 12.5, fontWeight: 600 }}>
            Guided setup →
          </Link>
        }
      >
        <p style={{ fontSize: 12.5, color: 'var(--text-dim)', marginTop: -8, marginBottom: 14 }}>
          Quick add below (name, type and chains only), or use guided setup for tasks and AI-drafted criteria.
        </p>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <input placeholder="Name" value={newProj.name} onChange={e => setNewProj({ ...newProj, name: e.target.value })} />
          <select value={newProj.type} onChange={e => setNewProj({ ...newProj, type: e.target.value })}>
            <option value="dapp">dApp</option>
            <option value="bridge">Bridge</option>
            <option value="lending">Lending</option>
            <option value="dex">DEX</option>
            <option value="other">Other</option>
          </select>
          <input placeholder="Chain IDs (comma sep)" value={newProj.chain_ids} onChange={e => setNewProj({ ...newProj, chain_ids: e.target.value })} style={{ minWidth: 180, flex: 1 }} />
          <button className="primary" onClick={add}>Add project</button>
        </div>
      </Card>

      <Card title="All projects">
        {!loaded && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {Array.from({ length: 3 }).map((_, i) => <div key={i} className="skeleton" style={{ height: 48, borderRadius: 10 }} />)}
          </div>
        )}
        {loaded && projects.length === 0 && (
          <EmptyState icon="◫" title="No projects yet" hint="Add a project above to start configuring tasks for it." />
        )}
        {loaded && projects.length > 0 && (
          <div className="table-scroll"><table>
            <thead><tr><th>Name</th><th>Type</th><th>Priority</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {projects.map(p => (
                <tr key={p.id}>
                  <td style={{ fontWeight: 600 }}>{p.name}</td>
                  <td><span className="badge neutral"><span className="badge-dot" />{p.type}</span></td>
                  <td className="mono">{p.priority}</td>
                  <td><Badge status={p.status === 'active'}>{p.status}</Badge></td>
                  <td style={{ textAlign: 'right' }}>
                    <Link to={`/projects/new?project=${p.id}`} style={{ fontSize: 12.5 }}>Draft criteria</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </Card>
    </div>
  )
}
