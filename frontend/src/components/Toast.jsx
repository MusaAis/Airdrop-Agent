import React, { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'

const ToastCtx = createContext(null)

export function ToastProvider({ children }) {
  const [items, setItems] = useState([])
  const idRef = useRef(0)

  const dismiss = useCallback(id => setItems(xs => xs.filter(x => x.id !== id)), [])
  const push = useCallback((kind, message, ms) => {
    const id = ++idRef.current
    setItems(xs => [...xs.slice(-3), { id, kind, message }])
    setTimeout(() => dismiss(id), ms ?? (kind === 'error' ? 7000 : 4000))
    return id
  }, [dismiss])

  const api = useMemo(() => ({
    success: m => push('success', m),
    error: m => push('error', m),
    info: m => push('info', m),
  }), [push])

  return (
    <ToastCtx.Provider value={api}>
      {children}
      <div className="toast-region" role="status" aria-live="polite">
        {items.map(t => (
          <div key={t.id} className={`toast ${t.kind}`}>
            <span className="toast-msg">{t.message}</span>
            <button aria-label="Dismiss" onClick={() => dismiss(t.id)}>✕</button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastCtx)
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>')
  return ctx
}
