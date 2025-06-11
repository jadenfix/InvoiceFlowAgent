/**
 * TypeScript types for Exception Review frontend
 */

export interface InvoiceQueueItem {
  id: string;
  vendor_name?: string;
  invoice_number?: string;
  total_amount?: number;
  invoice_date?: string;
  matched_status: string;
  confidence_score?: number;
  created_at: string;
}

export interface InvoiceDetail {
  id: string;
  vendor_name?: string;
  invoice_number?: string;
  total_amount?: number;
  invoice_date?: string;
  due_date?: string;
  status: string;
  matched_status: string;
  file_path?: string;
  file_type?: string;
  
  // Extraction data
  extracted_vendor?: string;
  extracted_amount?: number;
  extracted_invoice_number?: string;
  extracted_date?: string;
  
  // Matching data
  confidence_score?: number;
  match_details?: string;
  
  // Review data
  reviewed_by?: string;
  reviewed_at?: string;
  review_notes?: string;
  
  // Timestamps
  created_at: string;
  updated_at: string;
}

export interface ReviewQueueResponse {
  items: InvoiceQueueItem[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface ReviewRequest {
  reviewed_by: string;
  review_notes?: string;
}

export interface ApproveRequest extends ReviewRequest {}

export interface RejectRequest extends ReviewRequest {
  review_notes: string;
}

export interface ReviewResponse {
  invoice_id: string;
  action: string;
  reviewed_by: string;
  reviewed_at: string;
  review_notes?: string;
}

export interface ApiError {
  error: string;
  message: string;
  request_id?: string;
  timestamp: string;
}

export interface ValidationError extends ApiError {
  details: Array<{
    field: string;
    message: string;
    type: string;
  }>;
}

export interface QueueFilters {
  vendor_filter?: string;
  date_from?: string;
  date_to?: string;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
}

export interface PaginationProps {
  page: number;
  page_size: number;
  total: number;
  has_next: boolean;
  has_prev: boolean;
  onPageChange: (page: number) => void;
}

export interface LoadingState {
  isLoading: boolean;
  error?: string;
}

export interface ReviewFormData {
  reviewed_by: string;
  review_notes: string;
} 