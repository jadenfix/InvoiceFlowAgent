# Exception Review Frontend

React TypeScript frontend for the Invoice Exception Review system. This module provides a user-friendly interface for AP staff to review, approve, and reject invoices that require manual attention.

## Features

- **Queue Management**: Filterable, sortable, and paginated invoice review queue
- **Detailed Invoice View**: Comprehensive display of invoice information and extraction data
- **Review Workflow**: Intuitive approve/reject interface with validation
- **Real-time Updates**: React Query integration for optimistic updates
- **Responsive Design**: Mobile-friendly interface with Tailwind CSS
- **Error Handling**: Comprehensive error states and retry mechanisms
- **Accessibility**: WCAG compliant interface with proper ARIA labels

## Architecture

### Technology Stack

- **React 18**: Modern React with hooks and context
- **TypeScript**: Type-safe development
- **React Router**: Client-side routing
- **React Query**: Server state management and caching
- **Tailwind CSS**: Utility-first CSS framework
- **Heroicons**: Consistent icon library
- **Date-fns**: Date formatting and manipulation

### Components Structure

```
src/exception/
├── components/          # Reusable UI components
│   ├── QueueTable.tsx   # Invoice queue table with filtering
│   ├── Pagination.tsx   # Pagination controls
│   ├── ReviewForm.tsx   # Approve/reject form
│   └── InvoiceViewer.tsx # Detailed invoice display
├── pages/               # Page components
│   ├── QueuePage.tsx    # Main queue page
│   └── DetailPage.tsx   # Invoice detail page
├── hooks/               # Custom React hooks
│   └── useApi.ts        # API integration hooks
├── utils/               # Utility functions
│   └── api.ts           # API client
├── types/               # TypeScript types
│   └── index.ts         # Type definitions
└── index.tsx            # Module entry point
```

## Installation & Setup

### Prerequisites

- Node.js 18+
- npm or yarn
- React application with routing setup

### Installation

1. **Install Dependencies** (if not already installed):
   ```bash
   npm install @tanstack/react-query react-router-dom
   npm install @heroicons/react date-fns
   npm install -D @types/react @types/react-dom
   ```

2. **Environment Variables**:
   Create `.env` file in the frontend root:
   ```env
   VITE_EXCEPTION_API_URL=http://localhost:8007
   ```

### Integration

1. **Add to Main App Router**:
   ```typescript
   import { ExceptionApp } from './exception';
   
   function App() {
     return (
       <Router>
         <Routes>
           <Route path="/exception/*" element={<ExceptionApp />} />
           {/* Other routes */}
         </Routes>
       </Router>
     );
   }
   ```

2. **Or Use Individual Components**:
   ```typescript
   import { QueuePage, DetailPage } from './exception';
   
   // Use in your existing routing structure
   ```

## Usage

### Queue Page

The queue page displays all invoices requiring review with advanced filtering and sorting capabilities.

**Features**:
- Pagination with configurable page sizes
- Vendor name filtering
- Date range filtering
- Sortable columns (vendor, amount, date, etc.)
- Status indicators with color coding
- Confidence score visualization

**URL**: `/exception/`

### Detail Page

The detail page shows comprehensive invoice information and provides review controls.

**Features**:
- Complete invoice details (original and extracted data)
- Matching information and confidence scores
- File information and download links
- Review form with validation
- Success/error feedback
- Navigation breadcrumbs

**URL**: `/exception/review/{invoiceId}`

## API Integration

### React Query Configuration

The module uses React Query for efficient server state management:

```typescript
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 3,
      staleTime: 30000, // 30 seconds
      gcTime: 300000,   // 5 minutes
    },
  },
});
```

### Available Hooks

#### `useReviewQueue(page, pageSize, filters)`

Fetches paginated review queue with filtering.

```typescript
const { data, isLoading, error, refetch } = useReviewQueue(1, 20, {
  vendor_filter: 'Acme',
  date_from: '2024-01-01',
  sort_by: 'created_at',
  sort_order: 'desc'
});
```

#### `useInvoiceDetail(invoiceId)`

Fetches detailed invoice information.

```typescript
const { data: invoice, isLoading, error } = useInvoiceDetail(invoiceId);
```

#### `useApproveInvoice()`

Mutation hook for approving invoices.

```typescript
const approveInvoice = useApproveInvoice();

const handleApprove = async () => {
  await approveInvoice.mutateAsync({
    invoiceId: 'uuid',
    request: {
      reviewed_by: 'john.doe@company.com',
      review_notes: 'Approved - matches PO'
    }
  });
};
```

#### `useRejectInvoice()`

Mutation hook for rejecting invoices.

```typescript
const rejectInvoice = useRejectInvoice();

const handleReject = async () => {
  await rejectInvoice.mutateAsync({
    invoiceId: 'uuid',
    request: {
      reviewed_by: 'jane.smith@company.com',
      review_notes: 'Rejected - amount mismatch'
    }
  });
};
```

## Component Usage Examples

### Queue Table Component

```typescript
import { QueueTable } from './exception';

function MyQueuePage() {
  const [filters, setFilters] = useState({});
  const { data, isLoading } = useReviewQueue(1, 20, filters);
  
  return (
    <QueueTable
      items={data?.items || []}
      isLoading={isLoading}
      filters={filters}
      onFiltersChange={setFilters}
      onViewInvoice={(id) => navigate(`/review/${id}`)}
    />
  );
}
```

### Review Form Component

```typescript
import { ReviewForm } from './exception';

function MyDetailPage() {
  const approveInvoice = useApproveInvoice();
  const rejectInvoice = useRejectInvoice();
  
  return (
    <ReviewForm
      invoiceId={invoiceId}
      isApproving={approveInvoice.isPending}
      isRejecting={rejectInvoice.isPending}
      onApprove={(request) => approveInvoice.mutateAsync({ invoiceId, request })}
      onReject={(request) => rejectInvoice.mutateAsync({ invoiceId, request })}
      onCancel={() => setShowForm(false)}
    />
  );
}
```

## Styling & Theming

### Tailwind CSS Classes

The components use a consistent design system with Tailwind CSS:

**Colors**:
- Primary: `blue-600`, `blue-700` (buttons, links)
- Success: `green-600`, `green-100` (approval states)
- Danger: `red-600`, `red-100` (rejection states)
- Warning: `yellow-600`, `yellow-100` (pending states)
- Gray: `gray-50` to `gray-900` (backgrounds, text)

**Layout**:
- Responsive grid system
- Card-based layouts with `rounded-lg` and `shadow-sm`
- Consistent spacing with `p-4`, `p-6`, `space-y-4`

### Custom Styling

To customize the appearance, override Tailwind classes:

```css
/* Custom styles for exception module */
.exception-card {
  @apply bg-white rounded-lg shadow-sm border border-gray-200;
}

.exception-button-primary {
  @apply bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 px-4 rounded-md;
}
```

## State Management

### Form State

Review forms use local React state with validation:

```typescript
const [formData, setFormData] = useState({
  reviewed_by: '',
  review_notes: ''
});

const [errors, setErrors] = useState({});

const validateForm = (action: 'approve' | 'reject') => {
  const newErrors = {};
  
  if (!formData.reviewed_by.trim()) {
    newErrors.reviewed_by = 'Reviewer name is required';
  }
  
  if (action === 'reject' && !formData.review_notes.trim()) {
    newErrors.review_notes = 'Review notes are required for rejection';
  }
  
  setErrors(newErrors);
  return Object.keys(newErrors).length === 0;
};
```

### Server State

React Query manages server state with automatic caching and revalidation:

```typescript
// Automatic cache invalidation after mutations
const approveInvoice = useMutation({
  mutationFn: approveInvoiceApi,
  onSuccess: () => {
    // Invalidate queue to show updated status
    queryClient.invalidateQueries(['review-queue']);
  }
});
```

## Error Handling

### API Error States

```typescript
if (error) {
  return (
    <div className="error-banner">
      <ExclamationTriangleIcon className="h-5 w-5 text-red-500" />
      <div>
        <h3>Error Loading Data</h3>
        <p>{error.message}</p>
        <button onClick={() => refetch()}>Retry</button>
      </div>
    </div>
  );
}
```

### Form Validation Errors

```typescript
{errors.review_notes && (
  <p className="mt-1 text-sm text-red-600">
    {errors.review_notes}
  </p>
)}
```

### Network Error Handling

```typescript
const { data, error, isLoading, refetch } = useReviewQueue(page, pageSize, filters);

// Show retry button on network errors
if (error) {
  return (
    <div className="text-center py-12">
      <p className="text-gray-500 mb-4">Failed to load data</p>
      <button 
        onClick={() => refetch()}
        className="btn-primary"
      >
        Retry
      </button>
    </div>
  );
}
```

## Testing

### Component Testing

```typescript
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReviewForm } from './ReviewForm';

const createTestQueryClient = () => new QueryClient({
  defaultOptions: { queries: { retry: false } }
});

test('validates required fields on reject', async () => {
  const queryClient = createTestQueryClient();
  
  render(
    <QueryClientProvider client={queryClient}>
      <ReviewForm
        invoiceId="test-id"
        isApproving={false}
        isRejecting={false}
        onApprove={jest.fn()}
        onReject={jest.fn()}
        onCancel={jest.fn()}
      />
    </QueryClientProvider>
  );
  
  fireEvent.click(screen.getByText('Reject Invoice'));
  
  expect(screen.getByText('Review notes are required for rejection')).toBeInTheDocument();
});
```

### E2E Testing with Playwright

```typescript
import { test, expect } from '@playwright/test';

test('review workflow', async ({ page }) => {
  await page.goto('/exception');
  
  // Check queue loads
  await expect(page.locator('[data-testid="queue-table"]')).toBeVisible();
  
  // Click view button
  await page.click('[data-testid="view-invoice-btn"]:first-child');
  
  // Start review
  await page.click('[data-testid="start-review-btn"]');
  
  // Fill form and approve
  await page.fill('[data-testid="reviewed-by"]', 'test@example.com');
  await page.fill('[data-testid="review-notes"]', 'Test approval');
  await page.click('[data-testid="approve-btn"]');
  
  // Check success message
  await expect(page.locator('[data-testid="success-message"]')).toBeVisible();
});
```

## Performance Optimization

### React Query Optimization

```typescript
// Prefetch queue data on hover
const prefetchInvoiceDetail = (invoiceId: string) => {
  queryClient.prefetchQuery({
    queryKey: ['invoice-detail', invoiceId],
    queryFn: () => exceptionApi.getInvoiceDetail(invoiceId),
    staleTime: 60000,
  });
};

<button 
  onMouseEnter={() => prefetchInvoiceDetail(invoice.id)}
  onClick={() => navigate(`/review/${invoice.id}`)}
>
  View
</button>
```

### Virtualization for Large Lists

For very large invoice lists, consider virtual scrolling:

```typescript
import { FixedSizeList as List } from 'react-window';

const VirtualizedQueue = ({ items }) => (
  <List
    height={600}
    itemCount={items.length}
    itemSize={60}
    itemData={items}
  >
    {InvoiceRow}
  </List>
);
```

## Accessibility

### ARIA Labels

```typescript
<button
  aria-label={`Approve invoice ${invoice.invoice_number}`}
  onClick={handleApprove}
>
  Approve
</button>
```

### Keyboard Navigation

```typescript
const handleKeyDown = (event: KeyboardEvent, action: () => void) => {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault();
    action();
  }
};

<div
  role="button"
  tabIndex={0}
  onKeyDown={(e) => handleKeyDown(e, handleClick)}
  onClick={handleClick}
>
  Clickable Element
</div>
```

### Screen Reader Support

```typescript
<div role="status" aria-live="polite">
  {isLoading ? 'Loading invoices...' : `${totalCount} invoices found`}
</div>
```

## Browser Support

- **Modern Browsers**: Chrome 90+, Firefox 88+, Safari 14+, Edge 90+
- **Mobile**: iOS 14+, Android 10+

## Contributing

1. Follow React best practices
2. Use TypeScript strict mode
3. Add proper prop validation
4. Include accessibility features
5. Write comprehensive tests
6. Update documentation

## License

This project is licensed under the MIT License. 