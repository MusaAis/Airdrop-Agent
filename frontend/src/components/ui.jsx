import React from 'react'

export function Badge({ status, children }) {
  const tone =
    status === 'active' || status === 'success' || status === true ? 'success' :
    status === 'paused' || status === 'pending' ? 'warning' :
    status === 'archived' || status === 'failed' || status === false ? 'danger' :
    'neutral'
  return (
    <span className={`badge ${tone}`}>
      <span className="badge-dot" />
      {children}
    </span>
  )
}

export function Card({ title, action, children, className = '' }) {
  return (
    <div className={`card fade-in ${className}`}>
      {(title || action) && (
        <div className="card-header">
          {title && <h3 style={{ fontSize: 15 }}>{title}</h3>}
          {action}
        </div>
      )}
      {children}
    </div>
  )
}

export function EmptyState({ icon = '◇', title, hint }) {
  return (
    <div className="empty-state">
      <div className="empty-icon">{icon}</div>
      <h4>{title}</h4>
      {hint && <p>{hint}</p>}
    </div>
  )
}

export function SkeletonRows({ rows = 4, cols = 4 }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, r) => (
        <tr key={r}>
          {Array.from({ length: cols }).map((_, c) => (
            <td key={c}><div className="skeleton" style={{ height: 14, width: c === 0 ? '40%' : '70%' }} /></td>
          ))}
        </tr>
      ))}
    </>
  )
}

export function StatTile({ label, value, sub, tone = 'default' }) {
  const color = {
    default: 'var(--text)',
    signal: 'var(--signal)',
    amber: 'var(--amber)',
    rose: 'var(--rose)',
    violet: 'var(--violet)',
  }[tone]
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <span style={{ fontSize: 11, color: 'var(--text-faint)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600 }}>{label}</span>
      <span className="mono" style={{ fontSize: 26, fontWeight: 600, color, lineHeight: 1 }}>{value}</span>
      {sub && <span style={{ fontSize: 12, color: 'var(--text-dim)' }}>{sub}</span>}
    </div>
  )
}
