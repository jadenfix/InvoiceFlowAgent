interface PaginationProps {
  page: number;
  page_size: number;
  total: number;
  has_next: boolean;
  has_prev: boolean;
  onPageChange: (page: number) => void;
}

export function Pagination({ page, page_size, total, has_next, has_prev, onPageChange }: PaginationProps) {
  const pages = Math.max(1, Math.ceil(total / page_size));
  return (
    <nav aria-label="Invoice queue pagination" className="flex items-center justify-between rounded-lg border bg-white px-4 py-3">
      <p className="text-sm text-gray-600">
        {total === 0 ? 'No invoices' : `${(page - 1) * page_size + 1}–${Math.min(page * page_size, total)} of ${total} invoices`}
      </p>
      <div className="flex items-center gap-3">
        <button type="button" className="rounded border px-3 py-2 disabled:opacity-40" disabled={!has_prev || page <= 1} onClick={() => onPageChange(page - 1)}>Previous</button>
        <span aria-live="polite" className="text-sm">Page {page} of {pages}</span>
        <button type="button" className="rounded border px-3 py-2 disabled:opacity-40" disabled={!has_next || page >= pages} onClick={() => onPageChange(page + 1)}>Next</button>
      </div>
    </nav>
  );
}
