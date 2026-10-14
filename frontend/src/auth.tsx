import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useContext, useMemo, type ReactNode } from 'react'
import { api, getToken, setToken } from './api'
import type { User } from './types'

interface AuthState {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  loginWithToken: (token: string) => Promise<void>
  logout: () => void
  canWrite: boolean
  isAdmin: boolean
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const { data: user, isLoading } = useQuery({
    queryKey: ['me'],
    queryFn: () => api<User>('/auth/me'),
    enabled: !!getToken(),
    retry: false,
  })

  const value = useMemo<AuthState>(() => {
    const loginWithToken = async (token: string) => {
      setToken(token)
      await qc.invalidateQueries({ queryKey: ['me'] })
      await qc.fetchQuery({ queryKey: ['me'], queryFn: () => api<User>('/auth/me') })
    }
    return {
      user: getToken() ? (user ?? null) : null,
      loading: !!getToken() && isLoading,
      canWrite: !!user && user.role !== 'readonly',
      isAdmin: user?.role === 'admin',
      loginWithToken,
      login: async (email, password) => {
        const form = new URLSearchParams({ username: email, password })
        const res = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: form,
        })
        const body = await res.json().catch(() => ({}))
        if (!res.ok) throw new Error(body.detail ?? 'Login failed')
        await loginWithToken(body.access_token)
      },
      logout: () => {
        setToken(null)
        qc.clear()
        window.location.href = '/login'
      },
    }
  }, [user, isLoading, qc])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth outside AuthProvider')
  return ctx
}
