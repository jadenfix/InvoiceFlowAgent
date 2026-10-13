import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactNode } from "react";
import { exceptionApi } from "../utils/api";
import {
  QUERY_KEYS,
  useReviewQueue,
  useInvoiceDetail,
  useApproveInvoice,
  useRejectInvoice,
} from "./useApi";
afterEach(() => {
  vi.restoreAllMocks();
});
function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, wrapper };
}
describe("review cache lifecycle", () => {
  it("fetches queue with defaults and explicit paging filters", async () => {
    const spy = vi.spyOn(exceptionApi, "getReviewQueue").mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
      has_next: false,
      has_prev: false,
    });
    const { wrapper } = setup();
    const h = renderHook(() => useReviewQueue(), { wrapper });
    await waitFor(() => expect(h.result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith(1, 20, {});
    h.unmount();
    const filters = { vendor_filter: "Acme" };
    const other = renderHook(() => useReviewQueue(2, 10, filters), { wrapper });
    await waitFor(() => expect(other.result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith(2, 10, filters);
  });
  it("disables detail lookup without an identifier and exposes authentication errors", async () => {
    const spy = vi
      .spyOn(exceptionApi, "getInvoiceDetail")
      .mockRejectedValue(new Error("Authentication required"));
    const { wrapper } = setup();
    const h = renderHook(() => useInvoiceDetail(null), { wrapper });
    expect(spy).not.toHaveBeenCalled();
    expect(h.result.current.fetchStatus).toBe("idle");
    h.unmount();
    const other = renderHook(() => useInvoiceDetail("invoice"), { wrapper });
    await waitFor(() => expect(other.result.current.isError).toBe(true));
    expect(other.result.current.error).toEqual(
      new Error("Authentication required"),
    );
  });
  it.each([
    ["approve", "APPROVED", useApproveInvoice],
    ["reject", "REJECTED", useRejectInvoice],
  ] as const)(
    "%s writes server identity to cached detail and invalidates the queue",
    async (action, status, hook) => {
      const { client, wrapper } = setup();
      const old = { id: "invoice", matched_status: "NEEDS_REVIEW" };
      client.setQueryData(QUERY_KEYS.invoiceDetail("invoice"), old);
      const queueKey = QUERY_KEYS.reviewQueue({ page: 1, page_size: 20 });
      client.setQueryData(queueKey, { items: [old] });
      const response = {
        invoice_id: "invoice",
        action,
        reviewed_by: "server@example.com",
        reviewed_at: "2025-01-01",
        review_notes: "Verified",
      };
      vi.spyOn(
        exceptionApi,
        action === "approve" ? "approveInvoice" : "rejectInvoice",
      ).mockResolvedValue(response);
      const h = renderHook(() => hook(), { wrapper });
      await act(() =>
        h.result.current.mutateAsync({
          invoiceId: "invoice",
          request: { reviewed_by: "client text", review_notes: "Verified" },
        }),
      );
      expect(client.getQueryData(QUERY_KEYS.invoiceDetail("invoice"))).toEqual({
        ...old,
        matched_status: status,
        reviewed_by: "server@example.com",
        reviewed_at: "2025-01-01",
        updated_at: "2025-01-01",
        review_notes: "Verified",
      });
      expect(client.getQueryState(queueKey)?.isInvalidated).toBe(true);
    },
  );
  it.each([
    ["approve", useApproveInvoice],
    ["reject", useRejectInvoice],
  ] as const)(
    "%s does not manufacture detail records when no cache exists",
    async (action, hook) => {
      const { client, wrapper } = setup();
      vi.spyOn(
        exceptionApi,
        action === "approve" ? "approveInvoice" : "rejectInvoice",
      ).mockResolvedValue({
        invoice_id: "invoice",
        action,
        reviewed_by: "server",
        reviewed_at: "now",
      });
      const h = renderHook(() => hook(), { wrapper });
      await act(() =>
        h.result.current.mutateAsync({
          invoiceId: "invoice",
          request: { reviewed_by: "user", review_notes: "note" },
        }),
      );
      expect(
        client.getQueryData(QUERY_KEYS.invoiceDetail("invoice")),
      ).toBeUndefined();
    },
  );
  it("preserves pending detail on a rejected write and does not retry it", async () => {
    const { client, wrapper } = setup();
    const original = { id: "invoice", matched_status: "NEEDS_REVIEW" };
    client.setQueryData(QUERY_KEYS.invoiceDetail("invoice"), original);
    const spy = vi
      .spyOn(exceptionApi, "approveInvoice")
      .mockRejectedValue(new Error("Invoice already reviewed"));
    const h = renderHook(() => useApproveInvoice(), { wrapper });
    await act(async () => {
      await expect(
        h.result.current.mutateAsync({
          invoiceId: "invoice",
          request: { reviewed_by: "user" },
        }),
      ).rejects.toThrow("Invoice already reviewed");
    });
    expect(spy).toHaveBeenCalledOnce();
    expect(client.getQueryData(QUERY_KEYS.invoiceDetail("invoice"))).toEqual(
      original,
    );
  });
});
