import { useEffect, useRef, useState } from 'react'

function wsBase() {
  const env = import.meta.env.VITE_BACKEND_WS_URL
  if (env) return env.replace(/\/$/, '')
  // same origin: works behind the Vite dev proxy (/ws) and behind a reverse proxy in production
  return `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`
}

/**
 * Live stream from /ws/logs with automatic reconnect (1s → 30s backoff).
 * The server sends three event types:
 *   log        a row from the Log table      -> kept in `events` (newest first, de-duplicated by id)
 *   status     agent status on connect       -> `heartbeat`
 *   heartbeat  worker/memory pulse           -> `heartbeat`
 * Heartbeats are NOT added to `events`, so the feed only shows real activity.
 */
export default function useLiveFeed({ max = 150 } = {}) {
  const [connected, setConnected] = useState(false)
  const [events, setEvents] = useState([])
  const [heartbeat, setHeartbeat] = useState(null)
  const seen = useRef(new Set())

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
