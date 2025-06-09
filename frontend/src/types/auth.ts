/**
 * Authentication types for InvoiceFlow Frontend
 */

export interface User {
  id: number
  email: string
  full_name?: string
  is_active: boolean
  is_verified: boolean
  created_at: string
  updated_at: string
}

export interface LoginCredentials {
  email: string
  password: string
}

export interface RegisterData {
  email: string
  password: string
  full_name?: string
}

export interface AuthToken {
  access_token: string
  token_type: string
  expires_in: number
}

export interface AuthState {
  user: User | null
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null
}

export interface AuthError {
  error: string
  message: string
  field?: string
  details?: Array<{
    field: string
    message: string
  }>
  retry_after?: number
  type?: string
}

export interface ValidationErrors {
  [key: string]: string[]
}

// API Response types
export interface ApiResponse<T = any> {
  data?: T
  error?: string
  message?: string
  details?: any
}

export interface AuthApiError {
  response?: {
    status: number
    data: AuthError
  }
  message: string
  code?: string
}

// Form validation types
export interface LoginFormData {
  email: string
  password: string
}

export interface RegisterFormData {
  email: string
  password: string
  confirmPassword: string
  full_name?: string
}

export interface FormValidationState {
  isValid: boolean
  errors: Record<string, string>
  touched: Record<string, boolean>
} 