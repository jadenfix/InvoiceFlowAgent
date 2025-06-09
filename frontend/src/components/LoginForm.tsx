/**
 * Login form component with comprehensive validation and error handling
 */
import React, { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { Eye, EyeOff, LogIn, Loader2, AlertCircle } from 'lucide-react'
import { useAuth } from '@/stores/authStore'
import type { LoginFormData } from '@/types/auth'

interface LocationState {
  from?: string
}

export const LoginForm: React.FC = () => {
  const navigate = useNavigate()
  const location = useLocation()
  const { login, isLoading, error, clearError } = useAuth()
  
  const [showPassword, setShowPassword] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  
  const from = (location.state as LocationState)?.from || '/dashboard'

  const {
    register,
    handleSubmit,
    formState: { errors, isValid, isDirty },
    reset,
  } = useForm<LoginFormData>({
    mode: 'onBlur',
    defaultValues: {
      email: '',
      password: '',
    },
  })



  // Clear errors when form changes
  useEffect(() => {
    if (isDirty) {
      clearError()
      setFormError(null)
    }
  }, [isDirty, clearError])

  // Handle form submission
  const onSubmit = async (data: LoginFormData) => {
    try {
      setFormError(null)
      await login(data)
      
      // Successful login - navigate to intended destination
      navigate(from, { replace: true })
      
    } catch (loginError) {
      const errorMessage = loginError instanceof Error 
        ? loginError.message 
        : 'Login failed. Please try again.'
      
      setFormError(errorMessage)
    }
  }

  // Email validation
  const validateEmail = (email: string) => {
    const emailRegex = /^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i
    if (!emailRegex.test(email)) {
      return 'Please enter a valid email address'
    }
    return true
  }

  // Toggle password visibility
  const togglePasswordVisibility = () => {
    setShowPassword(!showPassword)
  }

  const displayError = formError || error

  return (
    <div className="w-full max-w-md mx-auto">
      <div className="bg-white shadow-xl rounded-lg p-8">
        <div className="text-center mb-8">
          <h2 className="text-3xl font-bold text-gray-900">Welcome Back</h2>
          <p className="text-gray-600 mt-2">Sign in to your InvoiceFlow account</p>
        </div>

        {displayError && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-md">
            <div className="flex">
              <AlertCircle className="h-5 w-5 text-red-400 mr-2 mt-0.5 flex-shrink-0" />
              <div className="text-sm text-red-700">{displayError}</div>
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-6" noValidate>
          {/* Email Field */}
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-2">
              Email Address
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              className={`
                w-full px-3 py-2 border rounded-md shadow-sm placeholder-gray-400
                focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500
                ${errors.email ? 'border-red-300' : 'border-gray-300'}
                ${isLoading ? 'bg-gray-50 cursor-not-allowed' : 'bg-white'}
              `}
              placeholder="Enter your email"
              disabled={isLoading}
              {...register('email', {
                required: 'Email is required',
                validate: validateEmail,
              })}
            />
            {errors.email && (
              <p className="mt-1 text-sm text-red-600">{errors.email.message}</p>
            )}
          </div>

          {/* Password Field */}
          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-2">
              Password
            </label>
            <div className="relative">
              <input
                id="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                className={`
                  w-full px-3 py-2 pr-10 border rounded-md shadow-sm placeholder-gray-400
                  focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500
                  ${errors.password ? 'border-red-300' : 'border-gray-300'}
                  ${isLoading ? 'bg-gray-50 cursor-not-allowed' : 'bg-white'}
                `}
                placeholder="Enter your password"
                disabled={isLoading}
                {...register('password', {
                  required: 'Password is required',
                  minLength: {
                    value: 1,
                    message: 'Password cannot be empty',
                  },
                })}
              />
              <button
                type="button"
                className="absolute inset-y-0 right-0 pr-3 flex items-center"
                onClick={togglePasswordVisibility}
                disabled={isLoading}
                tabIndex={-1}
              >
                {showPassword ? (
                  <EyeOff className="h-5 w-5 text-gray-400 hover:text-gray-600" />
                ) : (
                  <Eye className="h-5 w-5 text-gray-400 hover:text-gray-600" />
                )}
              </button>
            </div>
            {errors.password && (
              <p className="mt-1 text-sm text-red-600">{errors.password.message}</p>
            )}
          </div>

          {/* Submit Button */}
          <button
            type="submit"
            disabled={isLoading || !isValid}
            className={`
              w-full flex justify-center items-center py-2 px-4 border border-transparent 
              rounded-md shadow-sm text-sm font-medium text-white
              focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500
              ${
                isLoading || !isValid
                  ? 'bg-gray-400 cursor-not-allowed'
                  : 'bg-blue-600 hover:bg-blue-700'
              }
            `}
          >
            {isLoading ? (
              <>
                <Loader2 className="animate-spin h-4 w-4 mr-2" />
                Signing In...
              </>
            ) : (
              <>
                <LogIn className="h-4 w-4 mr-2" />
                Sign In
              </>
            )}
          </button>
        </form>

        {/* Additional Options */}
        <div className="mt-6 text-center">
          <p className="text-sm text-gray-600">
            Don&apos;t have an account?{' '}
            <button
              type="button"
              onClick={() => navigate('/register')}
              className="font-medium text-blue-600 hover:text-blue-500 focus:outline-none focus:underline"
              disabled={isLoading}
            >
              Sign up here
            </button>
          </p>
        </div>

        {/* Development Helper */}
        {process.env.NODE_ENV === 'development' && (
          <div className="mt-4 p-3 bg-gray-50 rounded-md text-xs text-gray-500">
            <p>Dev Helper: Email format required, any password accepted for demo</p>
            <button
              type="button"
              onClick={() => {
                reset({
                  email: 'demo@invoiceflow.com',
                  password: 'TestPassword123',
                })
              }}
              className="mt-1 text-blue-600 hover:text-blue-500"
            >
              Fill demo credentials
            </button>
          </div>
        )}
      </div>
    </div>
  )
} 