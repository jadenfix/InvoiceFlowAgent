import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Pagination } from "../Pagination";

describe("invoice pagination", () => {
  it("shows bounded records and disables unavailable navigation", () => {
    const onPageChange = vi.fn();
    render(
      <Pagination
        page={1}
        page_size={20}
        total={23}
        has_next
        has_prev={false}
        onPageChange={onPageChange}
      />,
    );
    expect(screen.getByText("1–20 of 23 invoices")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });
  it("stops at the last page even if server flags are inconsistent", () => {
    const onPageChange = vi.fn();
    render(
      <Pagination
        page={2}
        page_size={20}
        total={23}
        has_next
        has_prev
        onPageChange={onPageChange}
      />,
    );
    expect(screen.getByText("21–23 of 23 invoices")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Previous" }));
    expect(onPageChange).toHaveBeenCalledWith(1);
  });
});
it("does not navigate an empty queue even when server flags are inconsistent", () => {
  const onPageChange = vi.fn();
  render(
    <Pagination
      page={1}
      page_size={20}
      total={0}
      has_next={false}
      has_prev={false}
      onPageChange={onPageChange}
    />,
  );
  expect(screen.getByText("No invoices")).toBeInTheDocument();
  for (const b of screen.getAllByRole("button")) expect(b).toBeDisabled();
  expect(onPageChange).not.toHaveBeenCalled();
});
