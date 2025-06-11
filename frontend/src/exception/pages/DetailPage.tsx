/**
 * Detail Page - Page for reviewing individual invoices
 */

import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeftIcon, ExclamationTriangleIcon, CheckCircleIcon } from '@heroicons/react/24/outline';
import { useInvoiceDetail, useApproveInvoice, useRejectInvoice } from '../hooks/useApi';
import { InvoiceViewer } from '../components/InvoiceViewer';
import { ReviewForm } from '../components/ReviewForm';
import { ApproveRequest, RejectRequest } from '../types';

export function DetailPage() {
  const { invoiceId } = useParams<{ invoiceId: string }>();
  const navigate = useNavigate();
  const [showReviewForm, setShowReviewForm] = useState(false);
  const [showSuccessMessage, setShowSuccessMessage] = useState(false);
  const [successAction, setSuccessAction] = useState<string>('');

  const { 
    data: invoice, 
    isLoading, 
    error,
    refetch
  } = useInvoiceDetail(invoiceId || null);

  const approveInvoice = useApproveInvoice();
  const rejectInvoice = useRejectInvoice();

  // Show success message after successful action
  useEffect(() => {
    if (approveInvoice.isSuccess || rejectInvoice.isSuccess) {
      const action = approveInvoice.isSuccess ? 'approved' : 'rejected';
      setSuccessAction(action);
      setShowSuccessMessage(true);
      setShowReviewForm(false);
      
      // Hide success message after 5 seconds
      const timer = setTimeout(() => {
        setShowSuccessMessage(false);
      }, 5000);
      
      return () => clearTimeout(timer);
    }
  }, [approveInvoice.isSuccess, rejectInvoice.isSuccess]);

  const handleBack = () => {
    navigate('/exception');
  };

  const handleStartReview = () => {
    setShowReviewForm(true);
  };

  const handleCancelReview = () => {
    setShowReviewForm(false);
  };

  const handleApprove = async (request: ApproveRequest) => {
    if (!invoiceId) return;
    
    try {
      await approveInvoice.mutateAsync({ invoiceId, request });
    } catch (error) {
      console.error('Failed to approve invoice:', error);
      // Error will be handled by the mutation's error state
    }
  };

  const handleReject = async (request: RejectRequest) => {
    if (!invoiceId) return;
    
    try {
      await rejectInvoice.mutateAsync({ invoiceId, request });
    } catch (error) {
      console.error('Failed to reject invoice:', error);
      // Error will be handled by the mutation's error state
    }
  };

  // Handle loading state
  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="flex items-center space-x-2">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <span className="text-gray-600">Loading invoice details...</span>
        </div>
      </div>
    );
  }

  // Handle error state
  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="max-w-md w-full bg-white shadow-sm rounded-lg p-6">
          <div className="flex items-center">
            <ExclamationTriangleIcon className="h-6 w-6 text-red-500 mr-3" />
            <div>
              <h3 className="text-lg font-medium text-gray-900">
                Error Loading Invoice
              </h3>
              <p className="mt-1 text-sm text-gray-500">
                {error instanceof Error ? error.message : 'Failed to load invoice details'}
              </p>
            </div>
          </div>
          <div className="mt-4 flex space-x-3">
            <button
              onClick={() => refetch()}
              className="flex-1 py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
            >
              Retry
            </button>
            <button
              onClick={handleBack}
              className="flex-1 py-2 px-4 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
            >
              Go Back
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Handle not found
  if (!invoice) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="max-w-md w-full bg-white shadow-sm rounded-lg p-6 text-center">
          <ExclamationTriangleIcon className="h-12 w-12 text-gray-400 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-2">
            Invoice Not Found
          </h3>
          <p className="text-sm text-gray-500 mb-4">
            The requested invoice could not be found.
          </p>
          <button
            onClick={handleBack}
            className="w-full py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
          >
            Go Back to Queue
          </button>
        </div>
      </div>
    );
  }

  const isAlreadyReviewed = !!invoice.reviewed_by;
  const canReview = !isAlreadyReviewed && invoice.matched_status === 'NEEDS_REVIEW';

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-6">
          <button
            onClick={handleBack}
            className="inline-flex items-center text-sm text-gray-500 hover:text-gray-700 mb-4"
          >
            <ArrowLeftIcon className="h-4 w-4 mr-1" />
            Back to Queue
          </button>
          
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">
                Invoice Review
              </h1>
              <p className="mt-1 text-sm text-gray-500">
                Review invoice details and approve or reject
              </p>
            </div>
            
            {canReview && !showReviewForm && (
              <button
                onClick={handleStartReview}
                className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
              >
                Start Review
              </button>
            )}
          </div>
        </div>

        {/* Success Message */}
        {showSuccessMessage && (
          <div className="mb-6 rounded-md bg-green-50 p-4">
            <div className="flex">
              <div className="flex-shrink-0">
                <CheckCircleIcon className="h-5 w-5 text-green-400" />
              </div>
              <div className="ml-3">
                <h3 className="text-sm font-medium text-green-800">
                  Invoice {successAction} successfully
                </h3>
                <div className="mt-2 text-sm text-green-700">
                  <p>
                    The invoice has been {successAction} and the status has been updated.
                  </p>
                </div>
              </div>
              <div className="ml-auto pl-3">
                <div className="-mx-1.5 -my-1.5">
                  <button
                    onClick={() => setShowSuccessMessage(false)}
                    className="inline-flex bg-green-50 rounded-md p-1.5 text-green-500 hover:bg-green-100 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-green-50 focus:ring-green-600"
                  >
                    <span className="sr-only">Dismiss</span>
                    <svg className="h-3 w-3" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                    </svg>
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Error Messages */}
        {(approveInvoice.error || rejectInvoice.error) && (
          <div className="mb-6 rounded-md bg-red-50 p-4">
            <div className="flex">
              <div className="flex-shrink-0">
                <ExclamationTriangleIcon className="h-5 w-5 text-red-400" />
              </div>
              <div className="ml-3">
                <h3 className="text-sm font-medium text-red-800">
                  Review Failed
                </h3>
                <div className="mt-2 text-sm text-red-700">
                  <p>
                    {approveInvoice.error?.message || rejectInvoice.error?.message || 'An error occurred during review'}
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Invoice Details */}
          <div className="lg:col-span-2">
            <InvoiceViewer invoice={invoice} />
          </div>

          {/* Review Panel */}
          <div className="lg:col-span-1">
            {isAlreadyReviewed ? (
              <div className="bg-white border border-gray-200 rounded-lg p-6">
                <h3 className="text-lg font-medium text-gray-900 mb-4">
                  Review Complete
                </h3>
                <p className="text-sm text-gray-600">
                  This invoice has already been reviewed by {invoice.reviewed_by}.
                </p>
              </div>
            ) : !canReview ? (
              <div className="bg-white border border-gray-200 rounded-lg p-6">
                <h3 className="text-lg font-medium text-gray-900 mb-4">
                  Review Not Available
                </h3>
                <p className="text-sm text-gray-600">
                  This invoice is not in a state that requires review.
                </p>
              </div>
            ) : showReviewForm ? (
              <ReviewForm
                invoiceId={invoice.id}
                isApproving={approveInvoice.isPending}
                isRejecting={rejectInvoice.isPending}
                onApprove={handleApprove}
                onReject={handleReject}
                onCancel={handleCancelReview}
              />
            ) : (
              <div className="bg-white border border-gray-200 rounded-lg p-6">
                <h3 className="text-lg font-medium text-gray-900 mb-4">
                  Ready for Review
                </h3>
                <p className="text-sm text-gray-600 mb-4">
                  This invoice needs manual review. Please examine the details and click "Start Review" to approve or reject.
                </p>
                <button
                  onClick={handleStartReview}
                  className="w-full inline-flex justify-center items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                >
                  Start Review
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
} 