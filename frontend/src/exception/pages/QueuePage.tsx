/**
 * Queue Page - Main page for displaying invoices needing review
 */

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ExclamationTriangleIcon } from '@heroicons/react/24/outline';
import { useReviewQueue } from '../hooks/useApi';
import { QueueTable } from '../components/QueueTable';
import { Pagination } from '../components/Pagination';
import { QueueFilters } from '../types';

export function QueuePage() {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [filters, setFilters] = useState<QueueFilters>({});

  const { 
    data: queueData, 
    isLoading, 
    error,
    refetch
  } = useReviewQueue(page, pageSize, filters);

  const handleViewInvoice = (invoiceId: string) => {
    navigate(`/exception/review/${invoiceId}`);
  };

  const handlePageChange = (newPage: number) => {
    setPage(newPage);
  };

  const handleFiltersChange = (newFilters: QueueFilters) => {
    setFilters(newFilters);
    setPage(1); // Reset to first page when filters change
  };

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="max-w-md w-full bg-white shadow-sm rounded-lg p-6">
          <div className="flex items-center">
            <ExclamationTriangleIcon className="h-6 w-6 text-red-500 mr-3" />
            <div>
              <h3 className="text-lg font-medium text-gray-900">
                Error Loading Queue
              </h3>
              <p className="mt-1 text-sm text-gray-500">
                {error instanceof Error ? error.message : 'Failed to load review queue'}
              </p>
            </div>
          </div>
          <div className="mt-4">
            <button
              onClick={() => refetch()}
              className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
            >
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        {/* Page Header */}
        <div className="mb-8">
          <div className="md:flex md:items-center md:justify-between">
            <div className="flex-1 min-w-0">
              <h1 className="text-2xl font-bold leading-7 text-gray-900 sm:text-3xl sm:truncate">
                Exception Review Queue
              </h1>
              <p className="mt-1 text-sm text-gray-500">
                Review and approve/reject invoices that need manual attention
              </p>
            </div>
            <div className="mt-4 md:mt-0 md:ml-4">
              {queueData && (
                <div className="text-sm text-gray-500">
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                    {queueData.total} items pending review
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Main Content */}
        <div className="space-y-6">
          {/* Queue Table */}
          <QueueTable
            items={queueData?.items || []}
            isLoading={isLoading}
            filters={filters}
            onFiltersChange={handleFiltersChange}
            onViewInvoice={handleViewInvoice}
          />

          {/* Pagination */}
          {queueData && queueData.total > 0 && (
            <Pagination
              page={queueData.page}
              page_size={queueData.page_size}
              total={queueData.total}
              has_next={queueData.has_next}
              has_prev={queueData.has_prev}
              onPageChange={handlePageChange}
            />
          )}

          {/* Empty State */}
          {!isLoading && queueData && queueData.total === 0 && (
            <div className="text-center py-12">
              <ExclamationTriangleIcon className="mx-auto h-12 w-12 text-gray-400" />
              <h3 className="mt-2 text-sm font-medium text-gray-900">
                No invoices need review
              </h3>
              <p className="mt-1 text-sm text-gray-500">
                All invoices have been processed and reviewed.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
} 