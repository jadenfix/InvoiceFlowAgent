import { beforeEach, afterEach, describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { InvoiceViewer } from "../InvoiceViewer";
import { exceptionApi } from "../../utils/api";
import { InvoiceDetail } from "../../types";
const invoice: InvoiceDetail = {
  id: "invoice",
  vendor_name: "Acme",
  invoice_number: "INV-1",
  total_amount: 0,
  invoice_date: "2025-01-15",
  due_date: "2025-02-01",
  extracted_vendor: "Acme",
  extracted_amount: 123,
  extracted_invoice_number: "INV-1",
  extracted_date: "2025-01-15",
  confidence_score: 0.9,
  match_details: "Purchase order matched",
  file_path: "/document",
  file_type: "pdf",
  status: "COMPLETED",
  matched_status: "NEEDS_REVIEW",
  created_at: "2025-01-15T10:00:00Z",
  updated_at: "2025-01-15T11:00:00Z",
};
afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});
beforeEach(() => {
  URL.createObjectURL = vi.fn().mockReturnValue("blob:test");
  URL.revokeObjectURL = vi.fn();
});
describe("source invoice evidence", () => {
  it("shows zero amount instead of missing and renders extracted evidence", () => {
    render(<InvoiceViewer invoice={invoice} />);
    expect(screen.getByText("$0.00")).toBeInTheDocument();
    expect(screen.getByText("Purchase order matched")).toBeInTheDocument();
    expect(screen.getByText("90.0%")).toHaveClass("bg-green-100");
  });
  it.each([
    ["APPROVED", "bg-green-100"],
    ["AUTO_APPROVED", "bg-green-100"],
    ["REJECTED", "bg-red-100"],
    ["UNKNOWN", "bg-gray-100"],
  ])(
    "renders reviewed %s with server audit identity",
    (matched_status, color) => {
      render(
        <InvoiceViewer
          invoice={{
            ...invoice,
            matched_status,
            confidence_score: 0.7,
            reviewed_by: "reviewer@example.com",
            reviewed_at: "2025-01-16T12:00:00Z",
            review_notes: "Checked original",
          }}
        />,
      );
      expect(screen.getByText("reviewer@example.com")).toBeInTheDocument();
      expect(screen.getByText("Checked original")).toBeInTheDocument();
      expect(
        screen.getAllByText(matched_status.replace("_", " "))[0].parentElement,
      ).toHaveClass(color);
      expect(screen.getByText("70.0%")).toHaveClass("bg-yellow-100");
    },
  );
  it("handles absent optional evidence and malformed dates without crashing", () => {
    render(
      <InvoiceViewer
        invoice={{
          id: "missing",
          status: "COMPLETED",
          matched_status: "NEEDS_REVIEW",
          created_at: "invalid",
          updated_at: "",
          invoice_date: "invalid",
          reviewed_by: "reviewer",
          reviewed_at: "invalid",
          confidence_score: 0,
        }}
      />,
    );
    expect(screen.getAllByText("-").length).toBeGreaterThan(8);
    expect(screen.getByText("0.0%")).toHaveClass("bg-red-100");
    expect(
      screen.queryByRole("button", { name: "Download source PDF" }),
    ).not.toBeInTheDocument();
  });
  it("downloads authenticated bytes and releases the object URL", async () => {
    vi.useFakeTimers();
    const blob = new Blob(["%PDF-1.4"]);
    vi.spyOn(exceptionApi, "getDocument").mockResolvedValue(blob);
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
    render(<InvoiceViewer invoice={invoice} />);
    fireEvent.click(
      screen.getByRole("button", { name: "Download source PDF" }),
    );
    await vi.advanceTimersByTimeAsync(0);
    expect(exceptionApi.getDocument).toHaveBeenCalledWith("invoice");
    expect(click).toHaveBeenCalledOnce();
    expect(URL.createObjectURL).toHaveBeenCalledWith(blob);
    await vi.advanceTimersByTimeAsync(10000);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:test");
  });
  it.each([new Error("Session expired"), null])(
    "shows source download failures, never claims success (%s)",
    async (error) => {
      vi.spyOn(exceptionApi, "getDocument").mockRejectedValue(error);
      render(<InvoiceViewer invoice={invoice} />);
      fireEvent.click(
        screen.getByRole("button", { name: "Download source PDF" }),
      );
      await waitFor(() =>
        expect(screen.getByRole("alert")).toHaveTextContent(
          error instanceof Error ? "Session expired" : "Document unavailable.",
        ),
      );
      expect(URL.createObjectURL).not.toHaveBeenCalled();
    },
  );
});
