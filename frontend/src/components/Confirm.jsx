import React, { createContext, useCallback, useContext, useRef, useState } from 'react'
import { Modal } from './ui'

const ConfirmCtx = createContext(null)

/**
 * Replaces window.confirm everywhere.
 *   const confirm = useConfirm()
 *   if (!(await confirm({ title: 'Archive project?', message: '…', confirmLabel: 'Archive', tone: 'danger' }))) return
 */
export function ConfirmProvider({ children }) {
  const [state, setState] = useState(null)
  const resolver = useRef(null)

  const confirm = useCallback(opts => new Promise(resolve => {
    resolver.current = resolve
    setState(typeof opts === 'string' ? { message: opts } : opts)
  }), [])

  const close = ok => {
    resolver.current?.(ok)
    resolver.current = null
    setState(null)
  }

  return (
    <ConfirmCtx.Provider value={confirm}>
      {children}
      {state && (
        <Modal title={state.title || 'Are you sure?'} onClose={() => close(false)}>
          {state.message && <p className="hint" style={{ marginTop: 4 }}>{state.message}</p>}
          <div className="modal-actions">
            <button className="ghost" onClick={() => close(false)}>Cancel</button>
            <button
              className={state.tone === 'danger' ? 'danger solid' : 'primary'}
              onClick={() => close(true)}
              autoFocus
            >
              {state.confirmLabel || 'Confirm'}
            </button>
          </div>
        </Modal>
      )}
    </ConfirmCtx.Provider>
  )
}

export function useConfirm() {
  const ctx = useContext(ConfirmCtx)
  if (!ctx) throw new Error('useConfirm must be used inside <ConfirmProvider>')
  return ctx
}

/** A button that asks first. <ConfirmButton className="sm danger" title="Delete?" message="…" onConfirm={fn}>Delete</ConfirmButton> */
export function ConfirmButton({ title, message, confirmLabel, tone = 'danger', onConfirm, children, ...btn }) {
  const confirm = useConfirm()
  return (
    <button
      {...btn}
      onClick={async e => {
        e.stopPropagation()
        if (await confirm({ title, message, confirmLabel: confirmLabel || (typeof children === 'string' ? children : 'Confirm'), tone })) onConfirm?.()
      }}
    >
      {children}
    </button>
  )
}
