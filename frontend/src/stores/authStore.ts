/**
 * Authentication store using Zustand
 * Manages global authentication state with persistence
 */
import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import toast from 'react-hot-toast'
import { authService } from '@/services/auth'
import { 
  AuthState, 
  LoginCredentials, 
  RegisterData, 
  AuthToken 
} from '@/types/auth'

interface AuthActions {
  // Authentication actions
  login: (credentials: LoginCredentials) => Promise<void>
  register: (userData: RegisterData) => Promise<void>
  logout: () => Promise<void>
  
  // User management
  loadUser: () => Promise<void>
  refreshUser: () => Promise<void>
  
  // State management
  setLoading: (loading: boolean) => void
  setError: (error: string | null) => void
  clearError: () => void
  
  // Token management
  setToken: (token: string, expiresIn: number) => void
  clearToken: () => void
  checkTokenExpiry: () => boolean
}

interface AuthStore extends AuthState, AuthActions {}

const initialState: AuthState = {
  user: null,
  token: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set, get) => ({
      ...initialState,

      // Authentication actions
      login: async (credentials: LoginCredentials) => {
        set({ isLoading: true, error: null })
        
        try {
          const tokenData: AuthToken = await authService.login(credentials)
          
          // Store token with timestamp
          get().setToken(tokenData.access_token, tokenData.expires_in)
          
          // Load user data
          await get().loadUser()
          
          toast.success('Login successful!')
          
        } catch (error) {
          const errorMessage = error instanceof Error ? error.message : 'Login failed'
          set({ error: errorMessage })
          toast.error(errorMessage)
          throw error
        } finally {
          set({ isLoading: false })
        }
      },

      register: async (userData: RegisterData) => {
        set({ isLoading: true, error: null })
        
        try {
          await authService.register(userData)
          toast.success('Registration successful! Please log in.')
          
        } catch (error) {
          const errorMessage = error instanceof Error ? error.message : 'Registration failed'
          set({ error: errorMessage })
          toast.error(errorMessage)
          throw error
        } finally {
          set({ isLoading: false })
        }
      },

      logout: async () => {
        set({ isLoading: true })
        
        try {
          const { token } = get()
          if (token) {
            await authService.logout(token)
          }
          
          // Clear all auth state
          set({
            ...initialState,
            isLoading: false,
          })
          
          // Clear persisted data
          get().clearToken()
          
          toast.success('Logged out successfully')
          
        } catch (error) {
          // Even if logout fails on server, clear local state
          set({
            ...initialState,
            isLoading: false,
          })
          get().clearToken()
          
          console.warn('Logout error:', error)
          toast.success('Logged out')
        }
      },

      // User management
      loadUser: async () => {
        const { token } = get()
        if (!token) return
        
        set({ isLoading: true, error: null })
        
        try {
          const user = await authService.getCurrentUser(token)
          set({ 
            user, 
            isAuthenticated: true,
            isLoading: false 
          })
          
        } catch (error) {
          // Token might be invalid/expired
          console.warn('Failed to load user:', error)
          get().clearToken()
          set({
            ...initialState,
            isLoading: false,
            error: 'Session expired. Please log in again.'
          })
        }
      },

      refreshUser: async () => {
        if (get().isAuthenticated) {
          await get().loadUser()
        }
      },

      // State management
      setLoading: (loading: boolean) => set({ isLoading: loading }),
      
      setError: (error: string | null) => set({ error }),
      
      clearError: () => set({ error: null }),

      // Token management
      setToken: (token: string, expiresIn: number) => {
        const tokenTimestamp = Date.now()
        localStorage.setItem('auth_token', token)
        localStorage.setItem('auth_token_timestamp', tokenTimestamp.toString())
        localStorage.setItem('auth_token_expires_in', expiresIn.toString())
        
        set({ token, isAuthenticated: true })
      },

      clearToken: () => {
        localStorage.removeItem('auth_token')
        localStorage.removeItem('auth_token_timestamp')
        localStorage.removeItem('auth_token_expires_in')
        
        set({ 
          token: null, 
          user: null, 
          isAuthenticated: false 
        })
      },

      checkTokenExpiry: (): boolean => {
        const token = localStorage.getItem('auth_token')
        const timestampStr = localStorage.getItem('auth_token_timestamp')
        const expiresInStr = localStorage.getItem('auth_token_expires_in')
        
        if (!token || !timestampStr || !expiresInStr) {
          return true // Consider expired if missing data
        }
        
        const timestamp = parseInt(timestampStr, 10)
        const expiresIn = parseInt(expiresInStr, 10)
        
        return authService.isTokenExpired(timestamp, expiresIn)
      },
    }),
    {
      name: 'auth-storage',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        // Only persist essential data
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
      onRehydrateStorage: () => (state) => {
        // Restore token from localStorage and validate
        const token = localStorage.getItem('auth_token')
        
        if (token && state) {
          // Check if token is expired
          if (state.checkTokenExpiry()) {
            // Token expired, clear everything
            state.clearToken()
            state.setError('Session expired. Please log in again.')
          } else {
            // Token valid, restore it
            state.token = token
            // Optionally refresh user data
            state.loadUser().catch(() => {
              // If loading user fails, clear token
              state.clearToken()
            })
          }
        }
      },
    }
  )
)

// Auto-logout when token expires
const checkTokenExpiry = () => {
  const store = useAuthStore.getState()
  if (store.isAuthenticated && store.checkTokenExpiry()) {
    store.logout()
  }
}

// Check token expiry every minute
setInterval(checkTokenExpiry, 60000)

// Export hooks for common patterns
export const useAuth = () => {
  const store = useAuthStore()
  return {
    user: store.user,
    isAuthenticated: store.isAuthenticated,
    isLoading: store.isLoading,
    error: store.error,
    login: store.login,
    register: store.register,
    logout: store.logout,
    clearError: store.clearError,
  }
}

export const useAuthActions = () => {
  const store = useAuthStore()
  return {
    login: store.login,
    register: store.register,
    logout: store.logout,
    loadUser: store.loadUser,
    refreshUser: store.refreshUser,
    setLoading: store.setLoading,
    setError: store.setError,
    clearError: store.clearError,
  }
} 