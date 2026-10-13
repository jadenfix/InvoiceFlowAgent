# InvoiceFlow frontend

Connected signup/login, protected dashboard, real PDF upload/status, exception queue/filter/sort, detail review, authenticated source PDF download, approval/rejection and logout.

## Local pipeline

From the repository root start `docker compose -f docker-compose.pipeline.yml up -d --build --wait`. Then:

```sh
cd frontend
npm ci
VITE_AUTH_SERVICE_URL=http://127.0.0.1:8003 VITE_EXCEPTION_API_URL=http://127.0.0.1:8003 npm run dev -- --host 127.0.0.1
```

Open http://127.0.0.1:3000, create an account (password at least 12 characters), and sign in. Upload a valid text PDF containing Vendor, Invoice, PO, Total and Currency labeled lines. The local parser has no OCR/AI provider. Missing or mismatched purchase orders enter review. Manual approval is distinct from rule-based auto-approval. The server uses authenticated session identity for audit records.

## Verification

```sh
npm run lint
VITE_AUTH_SERVICE_URL=http://127.0.0.1:8003 VITE_EXCEPTION_API_URL=http://127.0.0.1:8003 npm run build
npx vitest run --threads false
npx playwright install chromium
node scripts/check-browser.cjs
```

The default browser runner requires the real pipeline on port 8003. It creates synthetic users/invoices and proves signup, invalid-password rejection, login, upload, review, source PDF download, approval, reload, removal from queue, logout and route protection at desktop/mobile widths. It never seeds an auth token to bypass login. `--fixture` intercepts HTTP contracts only for an isolated UI check and prints `UI_CONTRACT_FIXTURE`; that mode does not prove database/queue/extraction and is not used by durable-pipeline CI. Set CHROMIUM_PATH and PLAYWRIGHT_CORE_PATH for externally supplied browser runtimes. Screenshots go to temporary `/tmp` paths.

The exception coverage command enforces 95% for statements, lines, branches, and functions across `src/exception` runtime code. Types and tests are excluded; no runtime files are excluded. Run `npm run test:exception:coverage -- --threads false`. The behavior suite covers queue/loading/error/empty states, read-only completed reviews, approve/reject validation, cancellations, service and document failures, authenticated API headers, source-download cleanup, server audit identity, query-cache invalidation, pagination, date filters, and keyboard/pointer sorting. Current verified coverage: 100% statements/lines, 98.26% branches, 98.68% functions. Thresholds and collection scope remain unchanged. The durable real-pipeline CI job enforces this gate before its actual browser lane.
