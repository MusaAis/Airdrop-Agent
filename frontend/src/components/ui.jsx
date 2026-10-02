import React, { useEffect } from 'react'

/* ---------- Badge ---------- */
const TONE_BY_STATUS = {
  active: 'success', success: 'success', confirmed: 'success', applied: 'success', ok: 'success',
  paused: 'warning', pending: 'warning', suggested: 'warning', cooldown: 'warning',
  archived: 'danger', failed: 'danger', stopped: 'danger', blacklisted: 'danger', critical: 'danger',
}

export function Badge({ status, tone, children }) {
  const t =
    tone ||
    (status === true ? 'success' : status === false ? 'danger' : TONE_BY_STATUS[status]) ||
    'neutral'
  return (
    <span className={`badge ${t}`}>
      <span className="badge-dot" />
      {children}
    </span>
  )
}

/* ---------- Card ---------- */
export function Card({ title, action, children, className = '', flat, tight, style }) {
  return (
    <div className={`card fade-in ${flat ? 'flat' : ''} ${tight ? 'tight' : ''} ${className}`} style={style}>
      {(title || action) && (
        <div className="card-header">
          {title && <h3>{title}</h3>}
          {action}
        </div>
      )}
      {children}
    </div>
  )
}

/* ---------- Page header ---------- */
export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="page-header">
      <div>
        {title && <h2>{title}</h2>}
        {subtitle && <p>{subtitle}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  )
}

/* ---------- Form field ---------- */
export function Field({ label, hint, children, style }) {
  return (
    <label className="field" style={style}>
      {label && <span className="label">{label}</span>}
      {children}
      {hint && <span className="faint" style={{ fontSize: 11.5 }}>{hint}</span>}
    </label>
  )
}

/* ---------- Segmented control ---------- */
export function Segmented({ value, onChange, options }) {
  return (
    <div className="segmented" role="tablist">
      {options.map(o => {
        const v = typeof o === 'string' ? o : o.value
        const l = typeof o === 'string' ? o : o.label
        return (
          <button key={v} role="tab" aria-selected={value === v} className={value === v ? 'active' : ''} onClick={() => onChange(v)}>
            {l}
          </button>
        )
      })}
    </div>
  )
}

/* ---------- Meter ---------- */
export function Meter({ label, percent = 0, sub, tone }) {
  const color = tone || (percent > 85 ? 'var(--rose)' : percent > 65 ? 'var(--amber)' : 'var(--signal)')
  return (
    <div className="stack-sm" style={{ gap: 6 }}>
      {label && (
        <div className="row-between" style={{ fontSize: 12.5 }}>
          <span className="muted">{label}</span>
          <span className="mono" style={{ fontWeight: 600 }}>{Math.round(percent)}%</span>
        </div>
      )}
      <div className="meter"><div style={{ width: `${Math.max(0, Math.min(percent, 100))}%`, background: color }} /></div>
      {sub && <span className="faint" style={{ fontSize: 11.5 }}>{sub}</span>}
    </div>
  )
}

/* ---------- Empty / skeleton / stat ---------- */
export function EmptyState({ icon = '◇', title, hint, action }) {
  return (
    <div className="empty-state">
      <div className="empty-icon">{icon}</div>
      <h4>{title}</h4>
      {hint && <p>{hint}</p>}
      {action && <div style={{ marginTop: 14 }}>{action}</div>}
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

export function SkeletonBlock({ height = 60 }) {
  return <div className="skeleton" style={{ height, borderRadius: 10 }} />
}

export function StatTile({ label, value, sub, tone = 'default' }) {
  const color = { default: 'var(--text)', signal: 'var(--signal)', amber: 'var(--amber)', rose: 'var(--rose)', violet: 'var(--violet)' }[tone]
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <span className="stat-value" style={{ color }}>{value}</span>
      {sub && <span className="stat-sub">{sub}</span>}
    </div>
  )
}

/* ---------- Modal (bottom sheet on phones) ---------- */
export function Modal({ title, onClose, children, width }) {
  useEffect(() => {
    const onKey = e => { if (e.key === 'Escape') onClose?.() }
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = prev }
  }, [onClose])

  return (
    <div className="modal-scrim" onMouseDown={e => { if (e.target === e.currentTarget) onClose?.() }}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title} style={width ? { maxWidth: width } : undefined}>
        {title && <h3>{title}</h3>}
        {children}
      </div>
    </div>
  )
}

/* ---------- DataTable: a table on desktop, stacked cards on phones ----------
   columns: [{ key, label, render?(row), num?, actions?, className? }]
   expanded: row key currently expanded; renderExpanded(row) -> node            */
export function DataTable({
  columns, rows, rowKey = 'id', loading, skeletonRows = 4,
  onRowClick, expanded, renderExpanded, rowStyle, empty,
}) {
  const cellClass = c => [c.num ? 'num' : '', c.actions ? 'cell-actions' : '', c.className || ''].filter(Boolean).join(' ')
  return (
    <div className="table-scroll">
      <table className="rtable">
        <thead>
          <tr>{columns.map(c => <th key={c.key} className={c.num ? 'num' : ''}>{c.label}</th>)}</tr>
        </thead>
        <tbody>
          {loading && <SkeletonRows rows={skeletonRows} cols={columns.length} />}
          {!loading && rows.map(r => {
            const k = typeof rowKey === 'function' ? rowKey(r) : r[rowKey]
            return (
              <React.Fragment key={k}>
                <tr className={onRowClick ? 'clickable' : ''} style={rowStyle?.(r)} onClick={onRowClick ? () => onRowClick(r) : undefined}>
                  {columns.map(c => (
                    <td key={c.key} data-label={c.actions ? '' : c.label} className={cellClass(c)} onClick={c.actions ? e => e.stopPropagation() : undefined}>
                      {c.render ? c.render(r) : r[c.key]}
                    </td>
                  ))}
                </tr>
                {renderExpanded && expanded === k && (
                  <tr className="expand-row"><td colSpan={columns.length}>{renderExpanded(r)}</td></tr>
                )}
              </React.Fragment>
            )
          })}
        </tbody>
      </table>
      {!loading && rows.length === 0 && (empty || null)}
    </div>
  )
}

/* ---------- Icons (shared by sidebar + bottom nav) ---------- */
const PATHS = {
  dashboard:     'M3 13h8V3H3v10zm10 8h8V11h-8v10zM3 21h8v-6H3v6zm10-18v6h8V3h-8z',
  wallets:       'M21 7H3a1 1 0 0 0-1 1v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8a1 1 0 0 0-1-1zM3 5h14a2 2 0 0 1 2 2H3z M16.5 14.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z',
  balances:      'M12 1v22M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6',
  chains:        'M10.5 13.5l3-3m-5 6 2-2a4 4 0 0 0 0-5.66l-.34-.34a4 4 0 0 0-5.66 0l-2 2a4 4 0 0 0 0 5.66l.34.34M13.5 9.5l-2 2a4 4 0 0 0 0 5.66l.34.34a4 4 0 0 0 5.66 0l2-2a4 4 0 0 0 0-5.66l-.34-.34a4 4 0 0 0-5.66 0z',
  tasks:         'M9 11l3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11',
  projects:      'M3 7l9-4 9 4-9 4-9-4zm0 5l9 4 9-4M3 17l9 4 9-4',
  logs:          'M4 4h16v4H4zM4 11h10v9H4zM16 11h4v9h-4z',
  reports:       'M4 19h16M7 16v-5m5 5V8m5 8v-9',
  faucets:       'M12 2.5c3 4 6 7.5 6 11a6 6 0 1 1-12 0c0-3.5 3-7 6-11z',
  proxies:       'M8 9h8M8 9a3 3 0 1 1 0-6h1m7 6a3 3 0 1 0 0-6h-1M8 15h8m-8 0a3 3 0 1 0 0 6h1m7-6a3 3 0 1 1 0 6h-1',
  claims:        'M12 8v4l3 3m6-3a9 9 0 1 1-18 0 9 9 0 0 1 18 0z',
  ailog:         'M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 1 1 7.072 0l-.548.547A3.374 3.374 0 0 0 14 18.469V19a2 2 0 1 1-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z',
  sybil:         'M17 20h5v-2a3 3 0 0 0-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 0 1 5.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 0 1 9.288 0M15 7a3 3 0 1 1-6 0 3 3 0 0 1 6 0z',
  snapshot:      'M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2z',
  notifications: 'M15 17h5l-1.405-1.405A2.032 2.032 0 0 1 18 14.158V11a6.002 6.002 0 0 0-4-5.659V5a2 2 0 1 0-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 1 1-6 0v-1m6 0H9',
  settings:      'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 13a7.97 7.97 0 0 0 0-2l2-1.6-2-3.4-2.4 1a8 8 0 0 0-1.7-1L15 3h-4l-.3 2.4a8 8 0 0 0-1.7 1l-2.4-1-2 3.4 2 1.6a8 8 0 0 0 0 2l-2 1.6 2 3.4 2.4-1a8 8 0 0 0 1.7 1L11 21h4l.3-2.4a8 8 0 0 0 1.7-1l2.4 1 2-3.4-2-1.6z',
  more:          'M5 12h.01M12 12h.01M19 12h.01',
  logout:        'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9',
  collapse:      'M15 18l-6-6 6-6',
  refresh:       'M21 12a9 9 0 1 1-3-6.7M21 3v6h-6',
}

export function Icon({ name, size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={PATHS[name] || ''} />
    </svg>
  )
}
