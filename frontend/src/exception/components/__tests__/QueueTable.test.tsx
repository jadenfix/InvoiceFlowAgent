/**
 * Unit tests for QueueTable component
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueueTable } from '../QueueTable';
import { InvoiceQueueItem, QueueFilters } from '../../types';

// Mock data
const mockInvoices: InvoiceQueueItem[] = [
  {
    id: '123e4567-e89b-12d3-a456-426614174000',
    vendor_name: 'Acme Corp',
    invoice_number: 'INV-2024-001',
    total_amount: 1500.00,
    invoice_date: '2024-01-15T00:00:00Z',
    matched_status: 'NEEDS_REVIEW',
    confidence_score: 0.85,
    created_at: '2024-01-15T10:30:00Z'
  },
  {
    id: '456e7890-e89b-12d3-a456-426614174001',
    vendor_name: 'Tech Solutions Inc',
    invoice_number: 'INV-2024-002',
    total_amount: 2500.00,
    invoice_date: '2024-01-14T00:00:00Z',
    matched_status: 'NEEDS_REVIEW',
    confidence_score: 0.65,
    created_at: '2024-01-14T14:20:00Z'
  }
];

const defaultProps = {
  items: mockInvoices,
  isLoading: false,
  filters: {},
  onFiltersChange: jest.fn(),
  onViewInvoice: jest.fn(),
};

describe('QueueTable', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders invoice data correctly', () => {
    render(<QueueTable {...defaultProps} />);
    
    expect(screen.getByText('Acme Corp')).toBeInTheDocument();
    expect(screen.getByText('INV-2024-001')).toBeInTheDocument();
    expect(screen.getByText('$1,500.00')).toBeInTheDocument();
    expect(screen.getByText('85.0%')).toBeInTheDocument();
    
    expect(screen.getByText('Tech Solutions Inc')).toBeInTheDocument();
    expect(screen.getByText('INV-2024-002')).toBeInTheDocument();
    expect(screen.getByText('$2,500.00')).toBeInTheDocument();
    expect(screen.getByText('65.0%')).toBeInTheDocument();
  });

  it('shows loading state', () => {
    render(<QueueTable {...defaultProps} isLoading={true} items={[]} />);
    
    expect(screen.getByText('Loading...')).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { hidden: true })).toBeInTheDocument();
  });

  it('shows empty state when no items', () => {
    render(<QueueTable {...defaultProps} items={[]} />);
    
    expect(screen.getByText('No invoices need review')).toBeInTheDocument();
  });

  it('calls onViewInvoice when view button is clicked', () => {
    const onViewInvoice = jest.fn();
    render(<QueueTable {...defaultProps} onViewInvoice={onViewInvoice} />);
    
    const viewButtons = screen.getAllByText('View');
    fireEvent.click(viewButtons[0]);
    
    expect(onViewInvoice).toHaveBeenCalledWith('123e4567-e89b-12d3-a456-426614174000');
  });

  it('handles column sorting', () => {
    const onFiltersChange = jest.fn();
    render(<QueueTable {...defaultProps} onFiltersChange={onFiltersChange} />);
    
    const vendorHeader = screen.getByText('Vendor').closest('th');
    fireEvent.click(vendorHeader!);
    
    expect(onFiltersChange).toHaveBeenCalledWith({
      sort_by: 'vendor_name',
      sort_order: 'desc',
    });
  });

  it('toggles sort order when clicking same column', () => {
    const onFiltersChange = jest.fn();
    const filters: QueueFilters = {
      sort_by: 'vendor_name',
      sort_order: 'desc',
    };
    
    render(<QueueTable {...defaultProps} filters={filters} onFiltersChange={onFiltersChange} />);
    
    const vendorHeader = screen.getByText('Vendor').closest('th');
    fireEvent.click(vendorHeader!);
    
    expect(onFiltersChange).toHaveBeenCalledWith({
      sort_by: 'vendor_name',
      sort_order: 'asc',
    });
  });

  it('opens and closes filter panel', () => {
    render(<QueueTable {...defaultProps} />);
    
    const filtersButton = screen.getByText('Filters');
    fireEvent.click(filtersButton);
    
    expect(screen.getByPlaceholderText('Filter by vendor name')).toBeInTheDocument();
    expect(screen.getByText('From Date')).toBeInTheDocument();
    expect(screen.getByText('To Date')).toBeInTheDocument();
  });

  it('applies filters when filter form is submitted', async () => {
    const onFiltersChange = jest.fn();
    render(<QueueTable {...defaultProps} onFiltersChange={onFiltersChange} />);
    
    // Open filters
    fireEvent.click(screen.getByText('Filters'));
    
    // Fill in vendor filter
    const vendorInput = screen.getByPlaceholderText('Filter by vendor name');
    fireEvent.change(vendorInput, { target: { value: 'Acme' } });
    
    // Fill in date filter
    const fromDateInput = screen.getByLabelText('From Date');
    fireEvent.change(fromDateInput, { target: { value: '2024-01-01' } });
    
    // Apply filters
    fireEvent.click(screen.getByText('Apply Filters'));
    
    await waitFor(() => {
      expect(onFiltersChange).toHaveBeenCalledWith({
        vendor_filter: 'Acme',
        date_from: '2024-01-01',
      });
    });
  });

  it('clears filters when clear button is clicked', async () => {
    const onFiltersChange = jest.fn();
    const filters: QueueFilters = {
      vendor_filter: 'Acme',
      date_from: '2024-01-01',
    };
    
    render(<QueueTable {...defaultProps} filters={filters} onFiltersChange={onFiltersChange} />);
    
    // Open filters
    fireEvent.click(screen.getByText('Filters'));
    
    // Clear filters
    fireEvent.click(screen.getByText('Clear'));
    
    await waitFor(() => {
      expect(onFiltersChange).toHaveBeenCalledWith({});
    });
  });

  it('displays confidence scores with correct colors', () => {
    const itemsWithDifferentScores: InvoiceQueueItem[] = [
      { ...mockInvoices[0], confidence_score: 0.9 }, // High - green
      { ...mockInvoices[1], confidence_score: 0.7, id: '2' }, // Medium - yellow
      { ...mockInvoices[0], confidence_score: 0.4, id: '3' }, // Low - red
    ];
    
    render(<QueueTable {...defaultProps} items={itemsWithDifferentScores} />);
    
    const confidenceBadges = screen.getAllByText(/\d+\.\d+%/);
    
    // High confidence should have green background
    expect(confidenceBadges[0]).toHaveClass('bg-green-100', 'text-green-800');
    
    // Medium confidence should have yellow background
    expect(confidenceBadges[1]).toHaveClass('bg-yellow-100', 'text-yellow-800');
    
    // Low confidence should have red background
    expect(confidenceBadges[2]).toHaveClass('bg-red-100', 'text-red-800');
  });

  it('formats dates correctly', () => {
    render(<QueueTable {...defaultProps} />);
    
    expect(screen.getByText('Jan 15, 2024')).toBeInTheDocument();
    expect(screen.getByText('Jan 14, 2024')).toBeInTheDocument();
  });

  it('handles missing data gracefully', () => {
    const incompleteInvoice: InvoiceQueueItem = {
      id: 'incomplete-1',
      matched_status: 'NEEDS_REVIEW',
      created_at: '2024-01-15T10:30:00Z',
      // Missing optional fields
    };
    
    render(<QueueTable {...defaultProps} items={[incompleteInvoice]} />);
    
    // Should show dashes for missing data
    const rows = screen.getAllByRole('row');
    const dataRow = rows[1]; // Skip header row
    expect(dataRow).toHaveTextContent('-'); // For missing vendor_name
  });

  it('is accessible with proper ARIA labels', () => {
    render(<QueueTable {...defaultProps} />);
    
    // Check for table structure
    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.getAllByRole('columnheader')).toHaveLength(7);
    expect(screen.getAllByRole('row')).toHaveLength(3); // Header + 2 data rows
    
    // Check for button accessibility
    const viewButtons = screen.getAllByRole('button', { name: /view/i });
    expect(viewButtons).toHaveLength(2);
  });

  it('supports keyboard navigation', () => {
    render(<QueueTable {...defaultProps} />);
    
    const sortableHeaders = screen.getAllByRole('columnheader');
    const vendorHeader = sortableHeaders.find(header => 
      header.textContent?.includes('Vendor')
    );
    
    // Should be focusable
    expect(vendorHeader).toHaveAttribute('tabIndex', '0');
  });
}); 