import React, { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { LoginForm } from '@/components/LoginForm'

// Protected Route Component
interface ProtectedRouteProps {
  children: React.ReactNode
}

const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children }) => {
  const { isAuthenticated, isLoading } = useAuthStore()
  
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    )
  }
  
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />
}

// Dashboard Component (placeholder for now)
const Dashboard: React.FC = () => {
  const { user, logout } = useAuthStore()
  
  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex items-center">
              <h1 className="text-xl font-semibold text-gray-900">InvoiceFlow Agent Platform</h1>
            </div>
            <div className="flex items-center space-x-4">
              <span className="text-sm text-gray-600">Welcome, {user?.email}</span>
              <button
                onClick={() => logout()}
                className="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-md text-sm font-medium transition-colors"
              >
                Logout
              </button>
            </div>
          </div>
        </div>
      </nav>
      
      <main className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <div className="px-4 py-6 sm:px-0">
          <div className="border-4 border-dashed border-gray-200 rounded-lg h-96 flex items-center justify-center">
            <div className="text-center">
              <h2 className="text-2xl font-medium text-gray-900 mb-4">Dashboard Coming Soon</h2>
              <p className="text-gray-600">Your InvoiceFlow dashboard will be available here.</p>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}

// Main App Component
const App: React.FC = () => {
  const { checkTokenExpiry, clearToken, loadUser, token } = useAuthStore()
  
  // Check token expiry on app load and periodically
  useEffect(() => {
    const checkAuth = () => {
      if (checkTokenExpiry()) {
        clearToken()
      } else if (token) {
        loadUser().catch(() => clearToken())
      }
    }
    
    // Check immediately
    checkAuth()
    
    // Check every 5 minutes
    const interval = setInterval(checkAuth, 5 * 60 * 1000)
    
    return () => clearInterval(interval)
  }, [checkTokenExpiry, clearToken, loadUser, token])
  
  return (
    <div className="App">
      <Routes>
        <Route path="/login" element={<LoginForm />} />
        <Route 
          path="/dashboard" 
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          } 
        />
        <Route 
          path="/" 
          element={
            <ProtectedRoute>
              <Navigate to="/dashboard" replace />
            </ProtectedRoute>
          } 
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  )
}

export default App 