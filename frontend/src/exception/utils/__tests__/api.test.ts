import { afterEach, describe, expect, it, vi } from "vitest";
import { exceptionApi } from "../api";
afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});
describe("authenticated review contracts", () => {
  it("sends a real session token with review writes", async () => {
    localStorage.setItem("auth_token", "test-session");
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({ invoice_id: "invoice" }),
    } as Response);
    await exceptionApi.approveInvoice("invoice", {
      reviewed_by: "test@example.com",
      review_notes: "Checked source",
    });
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/invoice/approve"),
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: "Bearer test-session",
        }),
        body: JSON.stringify({
          reviewed_by: "test@example.com",
          review_notes: "Checked source",
        }),
      }),
    );
  });
  it("preserves service error detail without pretending success", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({ detail: "Invoice already reviewed" }),
    } as Response);
    await expect(
      exceptionApi.rejectInvoice("invoice", {
        reviewed_by: "test",
        review_notes: "Duplicate",
      }),
    ).rejects.toThrow("Invoice already reviewed");
  });
  it("fetches source bytes with authentication rather than opening a naked URL", async () => {
    localStorage.setItem("auth_token", "test-session");
    const pdf = new Blob(["%PDF-1.4"]);
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue({ ok: true, blob: async () => pdf } as Response);
    expect(await exceptionApi.getDocument("invoice")).toBe(pdf);
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/invoice/document"),
      expect.objectContaining({
        headers: { Authorization: "Bearer test-session" },
      }),
    );
  });
});
describe("queue input and failure boundaries", () => {
  it("encodes all query filters and uses default paging", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue({ ok: true, json: async () => ({}) } as Response);
    await exceptionApi.getReviewQueue();
    expect(String(fetch.mock.calls[0][0])).toContain("page=1&page_size=20");
    await exceptionApi.getReviewQueue(3, 10, {
      vendor_filter: "A&B",
      date_from: "2025-01-01",
      date_to: "2025-01-31",
      sort_by: "total_amount",
      sort_order: "asc",
    });
    const url = new URL(String(fetch.mock.calls[1][0]));
    expect(Object.fromEntries(url.searchParams)).toEqual({
      page: "3",
      page_size: "10",
      vendor_filter: "A&B",
      date_from: "2025-01-01",
      date_to: "2025-01-31",
      sort_by: "total_amount",
      sort_order: "asc",
    });
  });
  it("fetches detail and live health through the normal read contract", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({ status: "alive" }),
    } as Response);
    await exceptionApi.getInvoiceDetail("invoice");
    expect(fetch.mock.calls[0][0]).toContain("/review/invoice");
    expect(await exceptionApi.healthCheck()).toEqual({ status: "alive" });
    expect(fetch.mock.calls[1][0]).toContain("/health/live");
  });
  it.each([
    { message: "Forbidden", detail: "other" },
    { detail: ["validation object"] },
    {},
  ])("handles API error envelope %j", async (envelope) => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => envelope,
    } as Response);
    await expect(exceptionApi.getReviewQueue()).rejects.toThrow(
      envelope.message || "Request failed (HTTP 403)",
    );
  });
  it("handles a non-JSON gateway error", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 502,
      json: async () => {
        throw Error("HTML gateway response");
      },
    } as unknown as Response);
    await expect(exceptionApi.getReviewQueue()).rejects.toThrow(
      "Request failed (HTTP 502)",
    );
  });
  it("normalizes unknown network failures", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(null);
    await expect(exceptionApi.getReviewQueue()).rejects.toThrow(
      "Network error occurred",
    );
  });
  it("does not silently download an unauthorized source document", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 401,
    } as Response);
    await expect(exceptionApi.getDocument("invoice")).rejects.toThrow(
      "Document unavailable (HTTP 401)",
    );
  });
  it("supports source download without a stale stored token", async () => {
    const pdf = new Blob(["%PDF-1.4"]);
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue({ ok: true, blob: async () => pdf } as Response);
    expect(await exceptionApi.getDocument("a/b")).toBe(pdf);
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/a%2Fb/document"),
      { headers: {} },
    );
  });
});
