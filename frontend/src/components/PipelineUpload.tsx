import { FormEvent, useState } from "react";
import { useAuthStore } from "@/stores/authStore";
const base = (
  import.meta.env.VITE_EXCEPTION_API_URL || "http://localhost:8007"
).replace(/\/$/, "");
export function PipelineUpload() {
  const token = useAuthStore((s) => s.token);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const file = new FormData(event.currentTarget).get("file");
    if (!(file instanceof File) || file.size > 10 * 1024 * 1024) {
      setMessage("Choose a PDF up to 10 MB.");
      return;
    }
    setBusy(true);
    try {
      const body = new FormData();
      body.append("file", file);
      const response = await fetch(`${base}/api/v1/ingest/upload`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body,
      });
      const data = await response.json();
      if (!response.ok)
        throw Error(
          typeof data.detail === "string" ? data.detail : "Upload failed.",
        );
      setMessage(
        `Accepted ${data.request_id}. Waiting for extraction and matching…`,
      );
      for (let attempt = 0; attempt < 120; attempt++) {
        await new Promise((resolve) => setTimeout(resolve, 500));
        const statusResponse = await fetch(
          `${base}/api/v1/ingest/status/${encodeURIComponent(data.request_id)}`,
          { headers: { Authorization: `Bearer ${token}` } },
        );
        if (!statusResponse.ok)
          throw Error("Unable to check processing status.");
        const status = await statusResponse.json();
        if (status.status === "FAILED")
          throw Error(status.error || "PDF processing failed.");
        if (status.status === "COMPLETED") {
          setMessage(
            `Invoice ${data.request_id} processed. Open the queue to review any exception. Extraction: ${data.extraction_method || "see service status"}.`,
          );
          return;
        }
      }
      throw Error(
        `Invoice ${data.request_id} is still processing. Check the queue later.`,
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="mt-8 bg-white border rounded-lg p-6">
      <h2 className="text-xl font-semibold mb-3">Upload an invoice</h2>
      <p className="text-sm text-gray-600 mb-4">
        Connected pipeline requires a text PDF with Vendor, Invoice, PO, Total
        and Currency fields. Scanned documents require an OCR provider. Use
        synthetic data for the local demo.
      </p>
      <form onSubmit={upload} className="flex flex-wrap items-center gap-4">
        <label className="flex-1 min-w-0">
          Invoice PDF
          <input
            name="file"
            type="file"
            accept="application/pdf"
            required
            className="block mt-2 max-w-full"
          />
        </label>
        <button
          disabled={busy}
          className="rounded bg-blue-600 text-white px-4 py-2 disabled:opacity-50"
        >
          {busy ? "Processing…" : "Upload PDF"}
        </button>
      </form>
      <p role="status" className="mt-4 text-sm break-words">
        {message}
      </p>
    </section>
  );
}
