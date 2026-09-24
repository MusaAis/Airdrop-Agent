import React from 'react'

export default function Spinner({ inline = false, size = 16, label }) {
  const spinner = (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      style={{ animation: 'spin 0.8s linear infinite' }}
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.2" strokeWidth="3" fill="none" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" fill="none" />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </svg>
  )

  if (inline) {
    return (
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, color: 'inherit' }}>
        {spinner}
        {label}
      </span>
    )
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '1rem', color: 'var(--text-dim)' }}>
      {spinner}
      <span style={{ fontSize: 13 }}>{label || 'Loading…'}</span>
    </div>
  )
}
