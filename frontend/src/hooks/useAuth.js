import { useCallback, useEffect, useState } from 'react'

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

  // The API layer broadcasts this when a request comes back 401 (expired or
  // revoked token). Sync local state so guards stop treating us as signed in.
  useEffect(() => {
    const onUnauthorized = () => setUser(null)
    window.addEventListener('lg:unauthorized', onUnauthorized)
    return () => window.removeEventListener('lg:unauthorized', onUnauthorized)
  }, [])

  return {
    user,
    setSession,
    logout,
    isAuthed: Boolean(user),
    isAdmin: user?.role === 'admin',
  }
}
