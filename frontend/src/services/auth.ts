/**
 * Authentication service for InvoiceFlow Frontend
 * Handles login, registration, and token management
 */
import axios, { AxiosError, AxiosResponse } from 'axios'
import { 
  User, 
  LoginCredentials, 
  RegisterData, 
  AuthToken, 
  AuthError, 
  AuthApiError 
} from '@/types/auth'

// Configure axios instance for auth API
const authApi = axios.create({
  baseURL: '/auth',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Response interceptor for auth API
authApi.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error: AxiosError) => {
    // Handle network errors
    if (!error.response) {
      const networkError: AuthApiError = {
        message: 'Network error - please check your connection',
        code: 'NETWORK_ERROR',
      }
      return Promise.reject(networkError)
    }

    // Handle HTTP errors
    const authError: AuthApiError = {
      response: {
        status: error.response.status,
        data: error.response.data as AuthError,
      },
      message: error.message,
      code: error.code,
    }

    return Promise.reject(authError)
  }
)

class AuthService {
  /**
   * Login user with email and password
   */
  async login(credentials: LoginCredentials): Promise<AuthToken> {
    try {
      const response = await authApi.post<AuthToken>('/login', credentials)
      return response.data
    } catch (error) {
      const authError = error as AuthApiError
      
      // Enhanced error handling for different scenarios
      if (authError.response?.status === 401) {
        throw new Error('Invalid email or password')
      } else if (authError.response?.status === 423) {
        const lockoutData = authError.response.data
        throw new Error(
          `Account temporarily locked. Try again in ${lockoutData.retry_after} seconds.`
        )
      } else if (authError.response?.status === 429) {
        const rateLimitData = authError.response.data
        throw new Error(
          `Too many login attempts. Try again in ${rateLimitData.retry_after} seconds.`
        )
      } else if (authError.response?.status === 422) {
        const validationData = authError.response.data
        throw new Error(validationData.message || 'Invalid input data')
      } else if (authError.code === 'NETWORK_ERROR') {
        throw new Error('Unable to connect to authentication service')
      }
      
      throw new Error('Login failed. Please try again.')
    }
  }

  /**
   * Register new user
   */
  async register(userData: RegisterData): Promise<User> {
    try {
      const response = await authApi.post<User>('/register', userData)
      return response.data
    } catch (error) {
      const authError = error as AuthApiError
      
      if (authError.response?.status === 409) {
        throw new Error('An account with this email already exists')
      } else if (authError.response?.status === 422) {
        const validationData = authError.response.data
        if (validationData.details) {
          // Handle detailed validation errors
          const errors = validationData.details.map((detail: any) => detail.msg).join(', ')
          throw new Error(`Validation failed: ${errors}`)
        }
        throw new Error(validationData.message || 'Invalid registration data')
      } else if (authError.response?.status === 429) {
        const rateLimitData = authError.response.data
        throw new Error(
          `Too many registration attempts. Try again in ${rateLimitData.retry_after} seconds.`
        )
      } else if (authError.code === 'NETWORK_ERROR') {
        throw new Error('Unable to connect to authentication service')
      }
      
      throw new Error('Registration failed. Please try again.')
    }
  }

  /**
   * Get current user profile
   */
  async getCurrentUser(token: string): Promise<User> {
    try {
      const response = await authApi.get<User>('/me', {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })
      return response.data
    } catch (error) {
      const authError = error as AuthApiError
      
      if (authError.response?.status === 401) {
        throw new Error('Session expired. Please log in again.')
      } else if (authError.response?.status === 403) {
        throw new Error('Access denied. Account may be inactive.')
      } else if (authError.code === 'NETWORK_ERROR') {
        throw new Error('Unable to connect to authentication service')
      }
      
      throw new Error('Failed to retrieve user profile')
    }
  }

  /**
   * Logout user (client-side only for JWT)
   */
  async logout(token?: string): Promise<void> {
    try {
      if (token) {
        // Optional: Call server logout endpoint for logging
        await authApi.post('/logout', {}, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        })
      }
    } catch (error) {
      // Ignore logout errors - we'll clear local state anyway
      console.warn('Logout endpoint failed:', error)
    }
  }

  /**
   * Validate token by making a test request
   */
  async validateToken(token: string): Promise<boolean> {
    try {
      await this.getCurrentUser(token)
      return true
    } catch {
      return false
    }
  }

  /**
   * Check if token is expired based on expires_in
   */
  isTokenExpired(tokenTimestamp: number, expiresIn: number): boolean {
    const now = Date.now()
    const expirationTime = tokenTimestamp + (expiresIn * 1000)
    return now >= expirationTime
  }

  /**
   * Get auth service status
   */
  async getAuthStatus(): Promise<any> {
    try {
      const response = await authApi.get('/status')
      return response.data
    } catch (error) {
      throw new Error('Unable to check authentication service status')
    }
  }
}

// Export singleton instance
export const authService = new AuthService()
export default authService 