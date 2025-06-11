/**
 * API client for Exception Review Service
 */

import { 
  InvoiceDetail, 
  ReviewQueueResponse, 
  ApproveRequest, 
  RejectRequest,
  ReviewResponse,
  QueueFilters,
  ApiError 
} from '../types';

const BASE_URL = import.meta.env.VITE_EXCEPTION_API_URL || 'http://localhost:8007';

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(
    endpoint: string, 
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    
    const config: RequestInit = {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    };

    try {
      const response = await fetch(url, config);
      
      if (!response.ok) {
        const errorData: ApiError = await response.json();
        throw new Error(errorData.message || `HTTP ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      if (error instanceof Error) {
        throw error;
      }
      throw new Error('Network error occurred');
    }
  }

  async getReviewQueue(
    page: number = 1,
    pageSize: number = 20,
    filters: QueueFilters = {}
  ): Promise<ReviewQueueResponse> {
    const params = new URLSearchParams({
      page: page.toString(),
      page_size: pageSize.toString(),
    });

    // Add filters to params
    if (filters.vendor_filter) {
      params.append('vendor_filter', filters.vendor_filter);
    }
    if (filters.date_from) {
      params.append('date_from', filters.date_from);
    }
    if (filters.date_to) {
      params.append('date_to', filters.date_to);
    }
    if (filters.sort_by) {
      params.append('sort_by', filters.sort_by);
    }
    if (filters.sort_order) {
      params.append('sort_order', filters.sort_order);
    }

    return this.request<ReviewQueueResponse>(
      `/api/v1/review/queue?${params.toString()}`
    );
  }

  async getInvoiceDetail(invoiceId: string): Promise<InvoiceDetail> {
    return this.request<InvoiceDetail>(`/api/v1/review/${invoiceId}`);
  }

  async approveInvoice(
    invoiceId: string, 
    request: ApproveRequest
  ): Promise<ReviewResponse> {
    return this.request<ReviewResponse>(
      `/api/v1/review/${invoiceId}/approve`,
      {
        method: 'POST',
        body: JSON.stringify(request),
      }
    );
  }

  async rejectInvoice(
    invoiceId: string, 
    request: RejectRequest
  ): Promise<ReviewResponse> {
    return this.request<ReviewResponse>(
      `/api/v1/review/${invoiceId}/reject`,
      {
        method: 'POST',
        body: JSON.stringify(request),
      }
    );
  }

  async healthCheck(): Promise<{ status: string }> {
    return this.request<{ status: string }>('/health/live');
  }
}

export const exceptionApi = new ApiClient(BASE_URL); 