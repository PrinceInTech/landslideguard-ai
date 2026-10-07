import axios from 'axios'

export const API_BASE = import.meta.env.VITE_API_URL || ''

const api = axios.create({
  baseURL: API_BASE,
  timeout: 20000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('lg_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// An expired or revoked token used to leave the SPA holding a stale session:
// requests kept failing with 401 while the UI still looked signed in. Clear
// the session and let the app's route guard redirect to /login instead.
api.interceptors.response.use(
  (res) => res,
  (error) => {
    const status = error?.response?.status
    const url = error?.config?.url || ''
    // Do not treat a failed login attempt itself as a session expiry.
    const isAuthAttempt = /\/api\/auth\/(login|register)/.test(url)
    if (status === 401 && !isAuthAttempt) {
      localStorage.removeItem('lg_token')
      localStorage.removeItem('lg_user')
      // Let the in-app listener react without a full page reload.
      window.dispatchEvent(new CustomEvent('lg:unauthorized'))
    }
    return Promise.reject(error)
  }
)

export const setToken = (token) => localStorage.setItem('lg_token', token)
export const getToken = () => localStorage.getItem('lg_token')
export const clearToken = () => {
  localStorage.removeItem('lg_token')
  localStorage.removeItem('lg_user')
}

export default api
