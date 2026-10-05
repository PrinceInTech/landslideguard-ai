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

export const setToken = (token) => localStorage.setItem('lg_token', token)
export const getToken = () => localStorage.getItem('lg_token')
export const clearToken = () => localStorage.removeItem('lg_token')

export default api