/**
 * Invoice Viewer Component for displaying detailed invoice information
 */

import React from 'react';
import { format } from 'date-fns';
import { 
  DocumentTextIcon, 
  CurrencyDollarIcon, 
  CalendarIcon,
  UserIcon,
  ClockIcon,
  CheckCircleIcon,
  XCircleIcon
} from '@heroicons/react/24/outline';
import { InvoiceDetail } from '../types';

interface InvoiceViewerProps {
  invoice: InvoiceDetail;
}

export function InvoiceViewer({ invoice }: InvoiceViewerProps) {
  const formatDate = (dateString?: string) => {
    if (!dateString) return '-';
    try {
      return format(new Date(dateString), 'MMM dd, yyyy');
    } catch {
      return '-';
    }
  };

  const formatDateTime = (dateString?: string) => {
    if (!dateString) return '-';
    try {
      return format(new Date(dateString), 'MMM dd, yyyy HH:mm');
    } catch {
      return '-';
    }
  };

  const formatAmount = (amount?: number) => {
    if (!amount) return '-';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
    }).format(amount);
  };

  const formatConfidence = (score?: number) => {
    if (!score) return '-';
    return `${(score * 100).toFixed(1)}%`;
  };

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'auto_approved':
        return 'bg-green-100 text-green-800';
      case 'rejected':
        return 'bg-red-100 text-red-800';
      case 'needs_review':
        return 'bg-yellow-100 text-yellow-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status.toLowerCase()) {
      case 'auto_approved':
        return <CheckCircleIcon className="h-4 w-4" />;
      case 'rejected':
        return <XCircleIcon className="h-4 w-4" />;
      default:
        return <ClockIcon className="h-4 w-4" />;
    }
  };

  return (
    <div className="bg-white shadow-sm rounded-lg overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 bg-gray-50 border-b border-gray-200">
        <div className="flex items-center justify-between">
          <div className="flex items-center">
            <DocumentTextIcon className="h-6 w-6 text-gray-400 mr-3" />
            <div>
              <h2 className="text-lg font-medium text-gray-900">
                Invoice Details
              </h2>
              <p className="text-sm text-gray-500">
                ID: {invoice.id}
              </p>
            </div>
          </div>
          
          <div className="flex items-center space-x-2">
            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getStatusColor(invoice.matched_status)}`}>
              {getStatusIcon(invoice.matched_status)}
              <span className="ml-1">{invoice.matched_status.replace('_', ' ')}</span>
            </span>
          </div>
        </div>
      </div>

      <div className="p-6">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Left Column - Basic Info */}
          <div className="space-y-6">
            {/* Invoice Information */}
            <div>
              <h3 className="text-base font-medium text-gray-900 mb-4 flex items-center">
                <DocumentTextIcon className="h-5 w-5 text-gray-400 mr-2" />
                Invoice Information
              </h3>
              <dl className="space-y-3">
                <div className="flex justify-between">
                  <dt className="text-sm font-medium text-gray-500">Vendor:</dt>
                  <dd className="text-sm text-gray-900">{invoice.vendor_name || '-'}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-sm font-medium text-gray-500">Invoice Number:</dt>
                  <dd className="text-sm text-gray-900">{invoice.invoice_number || '-'}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-sm font-medium text-gray-500">Total Amount:</dt>
                  <dd className="text-sm text-gray-900 font-medium">
                    {formatAmount(invoice.total_amount)}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-sm font-medium text-gray-500">Invoice Date:</dt>
                  <dd className="text-sm text-gray-900">{formatDate(invoice.invoice_date)}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-sm font-medium text-gray-500">Due Date:</dt>
                  <dd className="text-sm text-gray-900">{formatDate(invoice.due_date)}</dd>
                </div>
              </dl>
            </div>

            {/* File Information */}
            <div>
              <h3 className="text-base font-medium text-gray-900 mb-4">
                File Information
              </h3>
              <dl className="space-y-3">
                <div className="flex justify-between">
                  <dt className="text-sm font-medium text-gray-500">File Type:</dt>
                  <dd className="text-sm text-gray-900">{invoice.file_type || '-'}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-sm font-medium text-gray-500">File Path:</dt>
                  <dd className="text-sm text-gray-900 break-all">{invoice.file_path || '-'}</dd>
                </div>
              </dl>
            </div>
          </div>

          {/* Right Column - Extraction & Matching */}
          <div className="space-y-6">
            {/* Extracted Data */}
            <div>
              <h3 className="text-base font-medium text-gray-900 mb-4">
                Extracted Data
              </h3>
              <dl className="space-y-3">
                <div className="flex justify-between">
                  <dt className="text-sm font-medium text-gray-500">Extracted Vendor:</dt>
                  <dd className="text-sm text-gray-900">{invoice.extracted_vendor || '-'}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-sm font-medium text-gray-500">Extracted Amount:</dt>
                  <dd className="text-sm text-gray-900">{formatAmount(invoice.extracted_amount)}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-sm font-medium text-gray-500">Extracted Invoice #:</dt>
                  <dd className="text-sm text-gray-900">{invoice.extracted_invoice_number || '-'}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-sm font-medium text-gray-500">Extracted Date:</dt>
                  <dd className="text-sm text-gray-900">{formatDate(invoice.extracted_date)}</dd>
                </div>
              </dl>
            </div>

            {/* Matching Information */}
            <div>
              <h3 className="text-base font-medium text-gray-900 mb-4">
                Matching Information
              </h3>
              <dl className="space-y-3">
                <div className="flex justify-between">
                  <dt className="text-sm font-medium text-gray-500">Confidence Score:</dt>
                  <dd className="text-sm text-gray-900">
                    <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                      (invoice.confidence_score || 0) > 0.8 
                        ? 'bg-green-100 text-green-800'
                        : (invoice.confidence_score || 0) > 0.6
                        ? 'bg-yellow-100 text-yellow-800'
                        : 'bg-red-100 text-red-800'
                    }`}>
                      {formatConfidence(invoice.confidence_score)}
                    </span>
                  </dd>
                </div>
                {invoice.match_details && (
                  <div>
                    <dt className="text-sm font-medium text-gray-500 mb-2">Match Details:</dt>
                    <dd className="text-sm text-gray-900">
                      <div className="bg-gray-50 p-3 rounded-md">
                        <pre className="whitespace-pre-wrap text-xs">
                          {invoice.match_details}
                        </pre>
                      </div>
                    </dd>
                  </div>
                )}
              </dl>
            </div>
          </div>
        </div>

        {/* Review Information (if reviewed) */}
        {invoice.reviewed_by && (
          <div className="mt-8 pt-6 border-t border-gray-200">
            <h3 className="text-base font-medium text-gray-900 mb-4 flex items-center">
              <UserIcon className="h-5 w-5 text-gray-400 mr-2" />
              Review Information
            </h3>
            <dl className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <dt className="text-sm font-medium text-gray-500">Reviewed By:</dt>
                <dd className="text-sm text-gray-900">{invoice.reviewed_by}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500">Reviewed At:</dt>
                <dd className="text-sm text-gray-900">{formatDateTime(invoice.reviewed_at)}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500">Status:</dt>
                <dd className="text-sm text-gray-900">
                  <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getStatusColor(invoice.matched_status)}`}>
                    {getStatusIcon(invoice.matched_status)}
                    <span className="ml-1">{invoice.matched_status.replace('_', ' ')}</span>
                  </span>
                </dd>
              </div>
            </dl>
            
            {invoice.review_notes && (
              <div className="mt-4">
                <dt className="text-sm font-medium text-gray-500 mb-2">Review Notes:</dt>
                <dd className="text-sm text-gray-900">
                  <div className="bg-gray-50 p-3 rounded-md">
                    {invoice.review_notes}
                  </div>
                </dd>
              </div>
            )}
          </div>
        )}

        {/* Timestamps */}
        <div className="mt-8 pt-6 border-t border-gray-200">
          <h3 className="text-base font-medium text-gray-900 mb-4 flex items-center">
            <CalendarIcon className="h-5 w-5 text-gray-400 mr-2" />
            Timestamps
          </h3>
          <dl className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <dt className="text-sm font-medium text-gray-500">Created At:</dt>
              <dd className="text-sm text-gray-900">{formatDateTime(invoice.created_at)}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">Updated At:</dt>
              <dd className="text-sm text-gray-900">{formatDateTime(invoice.updated_at)}</dd>
            </div>
          </dl>
        </div>
      </div>
    </div>
  );
} 