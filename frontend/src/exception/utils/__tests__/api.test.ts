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
