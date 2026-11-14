import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api } from './api.js'

// Who is logged in. `user` is undefined while checking, null when logged out.
const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined)
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    try {
      const data = await api.me()
      setUser(data.user)
      setError(null)
    } catch (e) {
      setError(e)
    }
  }, [])

  useEffect(() => {
    refresh()
    window.addEventListener('auth-changed', refresh)
    return () => window.removeEventListener('auth-changed', refresh)
  }, [refresh])

  const value = {
    user,
    error,
    refresh,
    setUser,
    logout: async () => {
      try {
        await api.logout()
      } finally {
        window.location.hash = '#/'
        setUser(null)
      }
    },
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)
