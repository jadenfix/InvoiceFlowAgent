/**
 * Review Form Component for approving/rejecting invoices
 */

import React, { useState } from 'react';
import { CheckCircleIcon, XCircleIcon } from '@heroicons/react/24/outline';
import { ApproveRequest, RejectRequest, ReviewFormData } from '../types';

interface ReviewFormProps {
  invoiceId: string;
  isApproving: boolean;
  isRejecting: boolean;
  onApprove: (request: ApproveRequest) => void;
  onReject: (request: RejectRequest) => void;
  onCancel: () => void;
}

export function ReviewForm({
  invoiceId,
  isApproving,
  isRejecting,
  onApprove,
  onReject,
  onCancel,
}: ReviewFormProps) {
  const [formData, setFormData] = useState<ReviewFormData>({
    reviewed_by: '',
    review_notes: '',
  });
  const [errors, setErrors] = useState<Record<string, string>>({});

  const validateForm = (action: 'approve' | 'reject'): boolean => {
    const newErrors: Record<string, string> = {};

    // Reviewed by is always required
    if (!formData.reviewed_by.trim()) {
      newErrors.reviewed_by = 'Reviewer name is required';
    }

    // Notes are required for rejection
    if (action === 'reject' && !formData.review_notes.trim()) {
      newErrors.review_notes = 'Review notes are required for rejection';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleApprove = () => {
    if (!validateForm('approve')) return;

    onApprove({
      reviewed_by: formData.reviewed_by.trim(),
      review_notes: formData.review_notes.trim() || undefined,
    });
  };

  const handleReject = () => {
    if (!validateForm('reject')) return;

    onReject({
      reviewed_by: formData.reviewed_by.trim(),
      review_notes: formData.review_notes.trim(),
    });
  };

  const handleInputChange = (field: keyof ReviewFormData, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    
    // Clear error when user starts typing
    if (errors[field]) {
      setErrors(prev => ({ ...prev, [field]: '' }));
    }
  };

  const isLoading = isApproving || isRejecting;

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-6">
      <h3 className="text-lg font-medium text-gray-900 mb-4">
        Review Invoice
      </h3>

      <div className="space-y-4">
        {/* Reviewer Name */}
        <div>
          <label htmlFor="reviewed_by" className="block text-sm font-medium text-gray-700 mb-1">
            Reviewer Name *
          </label>
          <input
            type="text"
            id="reviewed_by"
            value={formData.reviewed_by}
            onChange={(e) => handleInputChange('reviewed_by', e.target.value)}
            disabled={isLoading}
            placeholder="Enter your name"
            className={`block w-full border rounded-md shadow-sm px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 sm:text-sm ${
              errors.reviewed_by 
                ? 'border-red-300 focus:border-red-500' 
                : 'border-gray-300 focus:border-blue-500'
            } ${isLoading ? 'bg-gray-100 cursor-not-allowed' : 'bg-white'}`}
          />
          {errors.reviewed_by && (
            <p className="mt-1 text-sm text-red-600">{errors.reviewed_by}</p>
          )}
        </div>

        {/* Review Notes */}
        <div>
          <label htmlFor="review_notes" className="block text-sm font-medium text-gray-700 mb-1">
            Review Notes
            <span className="text-gray-500 ml-1">(Required for rejection)</span>
          </label>
          <textarea
            id="review_notes"
            rows={4}
            value={formData.review_notes}
            onChange={(e) => handleInputChange('review_notes', e.target.value)}
            disabled={isLoading}
            placeholder="Enter review comments or reasons for rejection..."
            className={`block w-full border rounded-md shadow-sm px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 sm:text-sm resize-vertical ${
              errors.review_notes 
                ? 'border-red-300 focus:border-red-500' 
                : 'border-gray-300 focus:border-blue-500'
            } ${isLoading ? 'bg-gray-100 cursor-not-allowed' : 'bg-white'}`}
          />
          {errors.review_notes && (
            <p className="mt-1 text-sm text-red-600">{errors.review_notes}</p>
          )}
        </div>

        {/* Action Buttons */}
        <div className="flex flex-col sm:flex-row gap-3 pt-4">
          <button
            onClick={handleApprove}
            disabled={isLoading}
            className={`inline-flex items-center justify-center px-6 py-3 border border-transparent rounded-md shadow-sm text-sm font-medium text-white focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500 ${
              isLoading
                ? 'bg-gray-400 cursor-not-allowed'
                : 'bg-green-600 hover:bg-green-700'
            }`}
          >
            {isApproving ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                Approving...
              </>
            ) : (
              <>
                <CheckCircleIcon className="h-5 w-5 mr-2" />
                Approve Invoice
              </>
            )}
          </button>

          <button
            onClick={handleReject}
            disabled={isLoading}
            className={`inline-flex items-center justify-center px-6 py-3 border border-transparent rounded-md shadow-sm text-sm font-medium text-white focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 ${
              isLoading
                ? 'bg-gray-400 cursor-not-allowed'
                : 'bg-red-600 hover:bg-red-700'
            }`}
          >
            {isRejecting ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                Rejecting...
              </>
            ) : (
              <>
                <XCircleIcon className="h-5 w-5 mr-2" />
                Reject Invoice
              </>
            )}
          </button>

          <button
            onClick={onCancel}
            disabled={isLoading}
            className={`inline-flex items-center justify-center px-6 py-3 border border-gray-300 rounded-md shadow-sm text-sm font-medium focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 ${
              isLoading
                ? 'text-gray-400 bg-gray-100 cursor-not-allowed'
                : 'text-gray-700 bg-white hover:bg-gray-50'
            }`}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
} 