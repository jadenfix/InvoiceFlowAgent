/**
 * Exception Review Module
 * Main entry point for the exception review functionality
 */

import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { QueuePage } from './pages/QueuePage';
import { DetailPage } from './pages/DetailPage';

// Create a query client instance
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 3,
      retryDelay: attemptIndex => Math.min(1000 * 2 ** attemptIndex, 30000),
      staleTime: 30000, // 30 seconds
      gcTime: 300000, // 5 minutes
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 1,
    },
  },
});

// Exception Review App Component
export function ExceptionApp() {
  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen bg-gray-50">
        <Routes>
          {/* Main queue page */}
          <Route path="/" element={<QueuePage />} />
          
          {/* Invoice detail/review page */}
          <Route path="/review/:invoiceId" element={<DetailPage />} />
          
          {/* Redirect any other paths to main queue */}
          <Route path="*" element={<Navigate to="/exception" replace />} />
        </Routes>
      </div>
    </QueryClientProvider>
  );
}

// Export components for external use
export { QueuePage } from './pages/QueuePage';
export { DetailPage } from './pages/DetailPage';
export { QueueTable } from './components/QueueTable';
export { InvoiceViewer } from './components/InvoiceViewer';
export { ReviewForm } from './components/ReviewForm';
export { Pagination } from './components/Pagination';

// Export hooks
export { 
  useReviewQueue, 
  useInvoiceDetail, 
  useApproveInvoice, 
  useRejectInvoice 
} from './hooks/useApi';

// Export types
export type {
  InvoiceQueueItem,
  InvoiceDetail,
  ReviewQueueResponse,
  ApproveRequest,
  RejectRequest,
  ReviewResponse,
  QueueFilters,
  ReviewFormData
} from './types';

// Export API client
export { exceptionApi } from './utils/api'; 