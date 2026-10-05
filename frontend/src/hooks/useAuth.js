import { useCallback, useState } from 'react'

export function useAuth() {
  const [user, setUser] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem('lg_user') || 'null')
    } catch {
      return null
    }
  })

  const setSession = useCallback((token, userObj) => {
    localStorage.setItem('lg_token', token)
    localStorage.setItem('lg_user', JSON.stringify(userObj))
    setUser(userObj)
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem('lg_token')
    localStorage.removeItem('lg_user')
    setUser(null)
  }, [])

  return { user, setSession, logout, isAuthed: Boolean(user) }
}