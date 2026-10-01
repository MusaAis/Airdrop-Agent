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
    const url = String(err.config?.url || '')
    if (err.response?.status === 401 && !url.includes('/auth/login')) {
      localStorage.removeItem('token')
      window.dispatchEvent(new Event('auth:expired'))
    }
    return Promise.reject(err)
  }
)

export default api
