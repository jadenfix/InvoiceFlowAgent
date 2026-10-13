import { beforeEach, afterEach, describe, it, expect, vi } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  act,
} from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { ExceptionApp } from "../../index";
import { DetailPage } from "../DetailPage";
const mocks = vi.hoisted(() => ({
  queue: vi.fn(),
  detail: vi.fn(),
  approve: vi.fn(),
  reject: vi.fn(),
}));
vi.mock("../../hooks/useApi", () => ({
  useReviewQueue: mocks.queue,
  useInvoiceDetail: mocks.detail,
  useApproveInvoice: mocks.approve,
  useRejectInvoice: mocks.reject,
}));
const invoice = {
  id: "invoice",
  vendor_name: "Acme",
  invoice_number: "INV-1",
  status: "COMPLETED",
  matched_status: "NEEDS_REVIEW",
  created_at: "2025-01-01",
  updated_at: "2025-01-01",
};
const queue = {
  items: [invoice],
  total: 21,
  page: 1,
  page_size: 20,
  has_next: true,
  has_prev: false,
};
let q: any, d: any, a: any, r: any;
function mount(route = "/exception") {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path="/exception/*" element={<ExceptionApp />} />
        <Route path="/without-id" element={<DetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}
function begin() {
  fireEvent.click(screen.getAllByRole("button", { name: "Start Review" })[0]);
  fireEvent.change(screen.getByLabelText(/Reviewer Name/), {
    target: { value: "Reviewer" },
  });
  fireEvent.change(screen.getByLabelText(/Review Notes/), {
    target: { value: "Verified source" },
  });
}
beforeEach(() => {
  q = { data: queue, isLoading: false, error: null, refetch: vi.fn() };
  d = { data: invoice, isLoading: false, error: null, refetch: vi.fn() };
  a = {
    isPending: false,
    isSuccess: false,
    error: null,
    mutateAsync: vi.fn().mockResolvedValue({}),
  };
  r = { ...a, mutateAsync: vi.fn().mockResolvedValue({}) };
  mocks.queue.mockImplementation(() => q);
  mocks.detail.mockImplementation(() => d);
  mocks.approve.mockImplementation(() => a);
  mocks.reject.mockImplementation(() => r);
});
afterEach(() => {
  vi.clearAllMocks();
  vi.useRealTimers();
});
describe("queue routing and controls", () => {
  it("routes an actual row into detail and back while preserving invoice identity", () => {
    mount();
    fireEvent.click(screen.getByRole("button", { name: "View" }));
    expect(mocks.detail).toHaveBeenCalledWith("invoice");
    expect(
      screen.getByRole("heading", { name: "Invoice Review" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Back to Queue" }));
    expect(
      screen.getByRole("heading", { name: "Exception Review Queue" }),
    ).toBeInTheDocument();
  });
  it("advances pagination and resets it when applying filters", () => {
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(mocks.queue).toHaveBeenLastCalledWith(2, 20, {});
    fireEvent.click(screen.getByRole("button", { name: "Filters" }));
    fireEvent.change(screen.getByLabelText("Vendor"), {
      target: { value: "Acme" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply Filters" }));
    expect(mocks.queue).toHaveBeenLastCalledWith(1, 20, {
      vendor_filter: "Acme",
    });
  });
  it("shows pending loading without falsely declaring an empty queue", () => {
    q = { ...q, isLoading: true, data: undefined };
    mount();
    expect(screen.getByLabelText("Loading invoices")).toBeInTheDocument();
    expect(
      screen.queryByText("All invoices have been processed and reviewed."),
    ).not.toBeInTheDocument();
  });
  it("reports an empty queue without asserting all historical invoices are complete", () => {
    q = { ...q, data: { ...queue, total: 0, items: [] } };
    mount();
    expect(
      screen.getByText(
        "There are currently no invoices in the manual review queue.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("navigation", { name: "Invoice queue pagination" }),
    ).not.toBeInTheDocument();
  });
  it.each([new Error("Authentication required"), "malformed failure"])(
    "offers retry for queue failures (%s)",
    (error) => {
      q = { ...q, error };
      mount();
      expect(
        screen.getByRole("heading", { name: "Error Loading Queue" }),
      ).toBeInTheDocument();
      expect(
        screen.getByText(
          error instanceof Error
            ? error.message
            : "Failed to load review queue",
        ),
      ).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Retry" }));
      expect(q.refetch).toHaveBeenCalledOnce();
    },
  );
  it("redirects unsupported routes to the queue", () => {
    mount("/exception/no-such-route");
    expect(
      screen.getByRole("heading", { name: "Exception Review Queue" }),
    ).toBeInTheDocument();
  });
});
describe("review state machine", () => {
  it("does not expose decisions while details are loading", () => {
    d = { ...d, data: undefined, isLoading: true };
    mount("/exception/review/invoice");
    expect(screen.getByText("Loading invoice details...")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Start Review" }),
    ).not.toBeInTheDocument();
  });
  it.each([new Error("Session expired"), null])(
    "recovers from unavailable or absent records (%s)",
    (error) => {
      d = { ...d, data: undefined, error };
      mount("/exception/review/invoice");
      if (error) {
        expect(screen.getByText("Session expired")).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Retry" }));
        expect(d.refetch).toHaveBeenCalledOnce();
        fireEvent.click(screen.getByRole("button", { name: "Go Back" }));
      } else {
        expect(
          screen.getByRole("heading", { name: "Invoice Not Found" }),
        ).toBeInTheDocument();
        fireEvent.click(
          screen.getByRole("button", { name: "Go Back to Queue" }),
        );
      }
      expect(
        screen.getByRole("heading", { name: "Exception Review Queue" }),
      ).toBeInTheDocument();
    },
  );
  it("handles non-Error detail failures without exposing review actions", () => {
    d = { ...d, error: "unstructured failure" };
    mount("/exception/review/invoice");
    expect(
      screen.getByText("Failed to load invoice details"),
    ).toBeInTheDocument();
  });
  it("handles missing route identifier without requesting a fabricated invoice", () => {
    d = { ...d, data: undefined };
    mount("/without-id");
    expect(mocks.detail).toHaveBeenCalledWith(null);
    expect(
      screen.getByRole("heading", { name: "Invoice Not Found" }),
    ).toBeInTheDocument();
  });
  it.each([
    { ...invoice, matched_status: "AUTO_APPROVED" },
    { ...invoice, reviewed_by: "server@example.com" },
  ])("withholds duplicate or unnecessary decisions for %j", (data) => {
    d = { ...d, data };
    mount("/exception/review/invoice");
    expect(
      screen.queryByRole("button", { name: "Start Review" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        name:
          "reviewed_by" in data ? "Review Complete" : "Review Not Available",
      }),
    ).toBeInTheDocument();
  });
  it("cancels an unsubmitted review without writing anything", () => {
    mount("/exception/review/invoice");
    begin();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(a.mutateAsync).not.toHaveBeenCalled();
    expect(r.mutateAsync).not.toHaveBeenCalled();
    expect(
      screen.getByRole("heading", { name: "Ready for Review" }),
    ).toBeInTheDocument();
  });
  it.each(["approve", "reject"])(
    "submits %s evidence and shows the confirmed outcome",
    async (action) => {
      vi.useFakeTimers();
      const result = mount("/exception/review/invoice");
      begin();
      fireEvent.click(
        screen.getByRole("button", {
          name: action === "approve" ? "Approve Invoice" : "Reject Invoice",
        }),
      );
      const mutation = action === "approve" ? a : r;
      expect(mutation.mutateAsync).toHaveBeenCalledWith({
        invoiceId: "invoice",
        request: { reviewed_by: "Reviewer", review_notes: "Verified source" },
      });
      await act(async () => {});
      mutation.isSuccess = true;
      d = { ...d, data: { ...invoice, reviewed_by: "server@example.com" } };
      result.rerender(
        <MemoryRouter>
          <Routes>
            <Route path="/exception/*" element={<ExceptionApp />} />
          </Routes>
        </MemoryRouter>,
      );
      expect(
        screen.getByText(
          `Invoice ${action === "approve" ? "approved" : "rejected"} successfully`,
        ),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("heading", { name: "Review Complete" }),
      ).toBeInTheDocument();
      if (action === "approve") {
        fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
      } else {
        await act(async () => vi.advanceTimersByTimeAsync(5000));
      }
      expect(
        screen.queryByText(
          `Invoice ${action === "approve" ? "approved" : "rejected"} successfully`,
        ),
      ).not.toBeInTheDocument();
    },
  );
  it.each(["approve", "reject"])(
    "keeps failures visible and never claims %s succeeded",
    async (action) => {
      const mutation = action === "approve" ? a : r;
      mutation.mutateAsync.mockRejectedValue(
        new Error("Invoice already reviewed"),
      );
      const log = vi.spyOn(console, "error").mockImplementation(() => {});
      const result = mount("/exception/review/invoice");
      begin();
      fireEvent.click(
        screen.getByRole("button", {
          name: action === "approve" ? "Approve Invoice" : "Reject Invoice",
        }),
      );
      await waitFor(() => expect(log).toHaveBeenCalled());
      mutation.error = new Error("Invoice already reviewed");
      result.rerender(
        <MemoryRouter>
          <Routes>
            <Route path="/exception/*" element={<ExceptionApp />} />
          </Routes>
        </MemoryRouter>,
      );
      expect(
        screen.getByRole("heading", { name: "Review Failed" }),
      ).toBeInTheDocument();
      expect(screen.getByText("Invoice already reviewed")).toBeInTheDocument();
      expect(screen.queryByText(/successfully/)).not.toBeInTheDocument();
      log.mockRestore();
    },
  );
  it("uses a readable fallback when a review error has an empty message", () => {
    a.error = new Error("");
    mount("/exception/review/invoice");
    expect(
      screen.getByText("An error occurred during review"),
    ).toBeInTheDocument();
  });
});
