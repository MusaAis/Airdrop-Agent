import { useEffect, useRef, useState } from 'react'
import api, { API_BASE } from '../api'

function wsBase() {
  // 1) explicit override, 2) derived from the REST base URL (https -> wss), 3) same origin
  //    (works behind the Vite dev proxy or a reverse proxy that serves both).
  const env = import.meta.env.VITE_BACKEND_WS_URL
  if (env) return env.replace(/\/$/, '')
  if (API_BASE && /^https?:\/\//.test(API_BASE)) return API_BASE.replace(/^http/, 'ws').replace(/\/$/, '')
  return `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`
}

/**
 * Live stream from /ws/logs with automatic reconnect (1s → 30s backoff).
 * The server sends three event types:
 *   log        a row from the Log table      -> kept in `events` (newest first, de-duplicated by id)
 *   status     agent status on connect       -> `heartbeat`
 *   heartbeat  worker/memory pulse           -> `heartbeat`
 * Heartbeats are NOT added to `events`, so the feed only shows real activity.
 * Recent history (default 50 rows) is loaded once from /ws/recent-logs, because the socket
 * itself only streams rows created after you connect.
 */
export default function useLiveFeed({ max = 150, history = 50 } = {}) {
  const [connected, setConnected] = useState(false)
  const [events, setEvents] = useState([])
  const [heartbeat, setHeartbeat] = useState(null)
  const seen = useRef(new Set())

  // The socket only streams NEW rows (it starts at the newest id), so load recent history once.
  useEffect(() => {
    if (!history) return
    let alive = true
    api.get('/ws/recent-logs', { params: { limit: history } })
      .then(r => {
        if (!alive || !Array.isArray(r.data)) return
        const rows = [...r.data].reverse() // endpoint is oldest -> newest; the feed is newest first
        setEvents(prev => {
          const have = new Set(prev.map(e => e.id))
          const fresh = rows.filter(e => !have.has(e.id))
          fresh.forEach(e => e.id != null && seen.current.add(e.id))
          return [...prev, ...fresh].slice(0, max)
        })
      })
      .catch(() => {})
    return () => { alive = false }
  }, [history, max])

  useEffect(() => {
    let ws = null
    let timer = null
    let attempt = 0
    let stopped = false

    const connect = () => {
      const token = localStorage.getItem('token')
      if (!token) return
      ws = new WebSocket(`${wsBase()}/ws/logs?token=${encodeURIComponent(token)}`)
      ws.onopen = () => { attempt = 0; setConnected(true) }
      ws.onmessage = e => {
        let msg
        try { msg = JSON.parse(e.data) } catch { return }
        if (msg.type === 'log' && msg.data) {
          const id = msg.data.id
          if (id != null) {
            if (seen.current.has(id)) return
            seen.current.add(id)
          }
          setEvents(prev => [msg.data, ...prev].slice(0, max))
        } else if (msg.type === 'heartbeat' || msg.type === 'status') {
          setHeartbeat(h => ({ ...(h || {}), ...msg.data }))
        }
      }
      ws.onclose = ev => {
        setConnected(false)
        if (stopped || ev.code === 4001) return // 4001 = bad token, retrying won't help
        attempt += 1
        timer = setTimeout(connect, Math.min(30000, 1000 * 2 ** Math.min(attempt, 5)))
      }
      ws.onerror = () => { try { ws.close() } catch { /* noop */ } }
    }

    connect()
    return () => { stopped = true; clearTimeout(timer); try { ws?.close() } catch { /* noop */ } }
  }, [max])

  return { connected, events, heartbeat }
}
