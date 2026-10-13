import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ReviewForm } from "../ReviewForm";
const setup = (extra = {}) => {
  const props = {
    invoiceId: "id",
    isApproving: false,
    isRejecting: false,
    onApprove: vi.fn(),
    onReject: vi.fn(),
    onCancel: vi.fn(),
    ...extra,
  };
  render(<ReviewForm {...props} />);
  return props;
};
describe("review decisions", () => {
  it("blocks blank reviewer and clears the error after editing", () => {
    const p = setup();
    fireEvent.click(screen.getByRole("button", { name: "Approve Invoice" }));
    expect(screen.getByText("Reviewer name is required")).toBeInTheDocument();
    expect(p.onApprove).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText(/Reviewer Name/), {
      target: { value: " reviewer@example.com " },
    });
    expect(
      screen.queryByText("Reviewer name is required"),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Approve Invoice" }));
    expect(p.onApprove).toHaveBeenCalledWith({
      reviewed_by: "reviewer@example.com",
      review_notes: undefined,
    });
  });
  it("requires substantive rejection notes and trims the audit record", () => {
    const p = setup();
    fireEvent.change(screen.getByLabelText(/Reviewer Name/), {
      target: { value: "Reviewer" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Reject Invoice" }));
    expect(
      screen.getByText("Review notes are required for rejection"),
    ).toBeInTheDocument();
    expect(p.onReject).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText(/Review Notes/), {
      target: { value: "  Duplicate invoice  " },
    });
    expect(
      screen.queryByText("Review notes are required for rejection"),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reject Invoice" }));
    expect(p.onReject).toHaveBeenCalledWith({
      reviewed_by: "Reviewer",
      review_notes: "Duplicate invoice",
    });
  });
  it("includes optional approval evidence and supports cancel", () => {
    const p = setup();
    fireEvent.change(screen.getByLabelText(/Reviewer Name/), {
      target: { value: "Reviewer" },
    });
    fireEvent.change(screen.getByLabelText(/Review Notes/), {
      target: { value: " Checked purchase order " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Approve Invoice" }));
    expect(p.onApprove).toHaveBeenCalledWith({
      reviewed_by: "Reviewer",
      review_notes: "Checked purchase order",
    });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(p.onCancel).toHaveBeenCalledOnce();
  });
  it.each(["isApproving", "isRejecting"])(
    "prevents concurrent decisions while %s",
    (key) => {
      const p = setup({ [key]: true });
      for (const button of screen.getAllByRole("button"))
        expect(button).toBeDisabled();
      expect(screen.getByLabelText(/Reviewer Name/)).toBeDisabled();
      expect(p.onApprove).not.toHaveBeenCalled();
      expect(p.onReject).not.toHaveBeenCalled();
    },
  );
});
