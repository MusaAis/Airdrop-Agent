import { useCallback, useEffect, useRef, useState } from 'react'

/** Pull a readable message out of an axios error. */
export function apiError(e, fallback = 'Request failed.') {
  const d = e?.response?.data?.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d)) return d.map(x => x?.msg || String(x)).join('; ')
  if (e?.message === 'Network Error') return 'Cannot reach the server.'
  return fallback
}

/**
 * Shared loading/error/refresh handling so pages stop re-implementing it.
 *
 *   const { data, loading, error, reload } = useApi(() => api.get('/x').then(r => r.data), [dep], { interval: 30000 })
 *
 * - `loading` is true only until the first response (use `refreshing` for later reloads)
 * - stale responses from an older call never overwrite a newer one
 * - polling pauses while the tab is hidden (saves battery on phones)
 */
export default function useApi(fn, deps = [], { interval = 0, initial = null } = {}) {
  const [data, setData] = useState(initial)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const fnRef = useRef(fn)
  fnRef.current = fn
  const seq = useRef(0)
  const alive = useRef(true)

  const reload = useCallback(async () => {
    const mine = ++seq.current
    setRefreshing(true)
    try {
      const r = await fnRef.current()
      if (alive.current && mine === seq.current) { setData(r); setError('') }
    } catch (e) {
      if (alive.current && mine === seq.current) setError(apiError(e))
    } finally {
      if (alive.current && mine === seq.current) { setLoading(false); setRefreshing(false) }
    }
  }, [])

  useEffect(() => {
    alive.current = true
    reload()
    let t
    if (interval > 0) {
      t = setInterval(() => { if (!document.hidden) reload() }, interval)
    }
    return () => { alive.current = false; if (t) clearInterval(t) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, interval])

  return { data, setData, error, loading, refreshing, reload }
}
