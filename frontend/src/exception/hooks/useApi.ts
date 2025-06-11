/**
 * React Query hooks for Exception Review API
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { 
  InvoiceDetail, 
  ReviewQueueResponse, 
  ApproveRequest, 
  RejectRequest,
  ReviewResponse,
  QueueFilters
} from '../types';
import { exceptionApi } from '../utils/api';

// Query keys
export const QUERY_KEYS = {
  reviewQueue: (filters: QueueFilters & { page: number; page_size: number }) => 
    ['review-queue', filters],
  invoiceDetail: (invoiceId: string) => ['invoice-detail', invoiceId],
} as const;

// Hook for review queue
export function useReviewQueue(
  page: number = 1,
  pageSize: number = 20,
  filters: QueueFilters = {}
) {
  return useQuery({
    queryKey: QUERY_KEYS.reviewQueue({ page, page_size: pageSize, ...filters }),
    queryFn: () => exceptionApi.getReviewQueue(page, pageSize, filters),
    staleTime: 30000, // 30 seconds
    gcTime: 300000, // 5 minutes
  });
}

// Hook for invoice detail
export function useInvoiceDetail(invoiceId: string | null) {
  return useQuery({
    queryKey: QUERY_KEYS.invoiceDetail(invoiceId!),
    queryFn: () => exceptionApi.getInvoiceDetail(invoiceId!),
    enabled: !!invoiceId,
    staleTime: 60000, // 1 minute
    gcTime: 300000, // 5 minutes
  });
}

// Hook for approving invoice
export function useApproveInvoice() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: ({ invoiceId, request }: { invoiceId: string; request: ApproveRequest }) =>
      exceptionApi.approveInvoice(invoiceId, request),
    onSuccess: (data: ReviewResponse) => {
      // Invalidate and refetch review queue
      queryClient.invalidateQueries({ 
        queryKey: ['review-queue'],
        exact: false 
      });
      
      // Update invoice detail cache
      queryClient.setQueryData(
        QUERY_KEYS.invoiceDetail(data.invoice_id),
        (oldData: InvoiceDetail | undefined) => {
          if (!oldData) return oldData;
          return {
            ...oldData,
            matched_status: 'AUTO_APPROVED',
            reviewed_by: data.reviewed_by,
            reviewed_at: data.reviewed_at,
            review_notes: data.review_notes,
            updated_at: data.reviewed_at,
          };
        }
      );
    },
  });
}

// Hook for rejecting invoice
export function useRejectInvoice() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: ({ invoiceId, request }: { invoiceId: string; request: RejectRequest }) =>
      exceptionApi.rejectInvoice(invoiceId, request),
    onSuccess: (data: ReviewResponse) => {
      // Invalidate and refetch review queue
      queryClient.invalidateQueries({ 
        queryKey: ['review-queue'],
        exact: false 
      });
      
      // Update invoice detail cache
      queryClient.setQueryData(
        QUERY_KEYS.invoiceDetail(data.invoice_id),
        (oldData: InvoiceDetail | undefined) => {
          if (!oldData) return oldData;
          return {
            ...oldData,
            matched_status: 'REJECTED',
            reviewed_by: data.reviewed_by,
            reviewed_at: data.reviewed_at,
            review_notes: data.review_notes,
            updated_at: data.reviewed_at,
          };
        }
      );
    },
  });
} 