import axios from 'axios'

export const API_BASE =
  import.meta.env.VITE_API_BASE_URL || ''

const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  withCredentials: true,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    // FastAPI sends 422 validation errors as an ARRAY in `detail`. Older pages put that
    // straight into state and render it, and React crashes on objects. Flatten it here
    // once so every `e.response.data.detail || '...'` stays a safe string.
    const d = err?.response?.data?.detail
    if (Array.isArray(d)) {
      err.response.data.detail = d.map(x => `${(x.loc || []).slice(1).join('.') || 'field'}: ${x.msg}`).join('; ')
    } else if (d && typeof d === 'object') {
      err.response.data.detail = JSON.stringify(d)
    }

    // Expired/invalid JWT (30 min lifetime): drop it and let <App> show the login screen
    // (no page reload needed - App listens for this event).
    const url = String(err?.config?.url || '')
    if (err?.response?.status === 401 && !url.includes('/auth/login')) {
      localStorage.removeItem('token')
      window.dispatchEvent(new Event('auth:expired'))
    }
    return Promise.reject(err)
  }
)

export default api
