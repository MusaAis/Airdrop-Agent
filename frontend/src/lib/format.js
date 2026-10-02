// Server timestamps are naive UTC ("2026-10-02T01:56:00"). Without a "Z" the
// browser reads them as LOCAL time, which shifts every time by the user's
// UTC offset. Always go through parseUtc().
export function parseUtc(iso) {
  if (!iso) return null
  // the API sometimes sends Python's str(datetime) ("2026-10-02 01:56:00.12") with a
  // space instead of "T" — Safari/iOS can't parse that, so normalise it first
  const s = String(iso).trim().replace(/^(\d{4}-\d\d-\d\d) /, '$1T')
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s : `${s}Z`)
}

export function timeAgo(iso) {
  const d = parseUtc(iso)
  if (!d || Number.isNaN(d.getTime())) return '—'
  const mins = Math.floor((Date.now() - d.getTime()) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

export function fmtDateTime(iso) {
  const d = parseUtc(iso)
  return d && !Number.isNaN(d.getTime()) ? d.toLocaleString() : '—'
}

export const shortAddr = a => (a && a.length > 12 ? `${a.slice(0, 6)}…${a.slice(-4)}` : a || '')
export const fmtUsd = v => (v == null || Number.isNaN(Number(v)) ? '—' : `$${Number(v).toFixed(2)}`)
export const fmtNum = n => (n == null ? '—' : Number(n).toLocaleString())

export const fmtTime = iso => {
  const d = parseUtc(iso)
  return d && !Number.isNaN(d.getTime()) ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—'
}
