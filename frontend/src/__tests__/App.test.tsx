import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import App from '../App';

const state = {
  isAuthenticated: true,
  isLoading: false,
  token: null,
  user: { email: 'reviewer@example.com' },
  logout: vi.fn(),
  checkTokenExpiry: () => false,
  clearToken: vi.fn(),
  loadUser: vi.fn().mockResolvedValue(undefined),
};
vi.mock('@/stores/authStore', () => ({ useAuthStore: () => state }));

describe('review workflow entry point', () => {
  it('opens the real review queue from the dashboard', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ items: [], total: 0, page: 1, page_size: 20, has_next: false, has_prev: false }),
    } as Response);
    try {
      render(<MemoryRouter initialEntries={['/dashboard']}><App /></MemoryRouter>);
      fireEvent.click(screen.getByRole('link', { name: 'Open review queue' }));
      expect(await screen.findByRole('heading', { name: 'Exception Review Queue' })).toBeInTheDocument();
      expect(await screen.findByText('All invoices have been processed and reviewed.')).toBeInTheDocument();
      expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/v1/review/queue'), expect.any(Object));
    } finally {
      fetchMock.mockRestore();
    }
  });
});
