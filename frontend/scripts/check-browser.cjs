/* Default lane calls the real pipeline. --fixture is UI-only contract verification. */
const { chromium } = require(
  process.env.PLAYWRIGHT_CORE_PATH || "playwright-core",
);
const { spawn } = require("node:child_process");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const fixture = process.argv.includes("--fixture");
const origin = "http://127.0.0.1:4173";
function pdf(number) {
  const lines = [
    "Vendor: Browser Acceptance",
    `Invoice: ${number}`,
    "PO: UNMATCHED-BROWSER-PO",
    "Total: 123.45",
    "Currency: USD",
  ];
  const stream =
    "BT /F1 12 Tf 50 740 Td " +
    lines.map((l) => `(${l}) Tj`).join(" 0 -24 Td ") +
    " ET";
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
    `<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
  ];
  let content = "%PDF-1.4\n",
    offsets = [0];
  objects.forEach((o, i) => {
    offsets.push(Buffer.byteLength(content));
    content += `${i + 1} 0 obj\n${o}\nendobj\n`;
  });
  const xref = Buffer.byteLength(content);
  content +=
    `xref\n0 6\n0000000000 65535 f \n` +
    offsets
      .slice(1)
      .map((o) => String(o).padStart(10, "0") + " 00000 n \n")
      .join("") +
    `trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(content);
}
async function mockContracts(page, email, number, document) {
  const now = new Date().toISOString();
  let reviewed = false,
    identity = {
      id: 1,
      email,
      is_active: true,
      is_verified: false,
      created_at: now,
      updated_at: now,
    };
  const item = {
    id: "fixture-invoice",
    vendor_name: "Browser Acceptance",
    invoice_number: number,
    total_amount: 123.45,
    matched_status: "NEEDS_REVIEW",
    created_at: now,
    status: "COMPLETED",
    file_path: "/api/v1/review/fixture-invoice/document",
    file_type: "pdf",
    match_details: '{"reason":"No PO"}',
    updated_at: now,
  };
  await page.route("http://127.0.0.1:8003/**", async (route) => {
    const req = route.request(),
      u = new URL(req.url()),
      headers = {
        "access-control-allow-origin": origin,
        "access-control-allow-headers": "Content-Type, Authorization",
      };
    let data = {},
      status = 200;
    if (req.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers });
      return;
    }
    if (u.pathname === "/auth/register") {
      status = 201;
      data = identity;
    } else if (u.pathname === "/auth/login") {
      if (req.postDataJSON().password === "WrongPassword123!") {
        status = 401;
        data = { detail: "Invalid email or password" };
      } else
        data = {
          access_token: "ui-fixture-token",
          token_type: "bearer",
          expires_in: 3600,
        };
    } else if (u.pathname === "/auth/me") data = identity;
    else if (u.pathname === "/auth/logout") data = { success: true };
    else if (u.pathname === "/api/v1/ingest/upload") {
      status = 202;
      data = {
        request_id: item.id,
        status: "PENDING",
        extraction_method: "UI_CONTRACT_FIXTURE",
      };
    } else if (u.pathname.startsWith("/api/v1/ingest/status/"))
      data = { ...item, fields: { extraction_method: "UI_CONTRACT_FIXTURE" } };
    else if (u.pathname === "/api/v1/review/queue")
      data = {
        items: reviewed ? [] : [item],
        total: reviewed ? 0 : 1,
        page: 1,
        page_size: 20,
        has_next: false,
        has_prev: false,
      };
    else if (u.pathname.endsWith("/document")) {
      assert.equal(req.headers().authorization, "Bearer ui-fixture-token");
      await route.fulfill({
        status,
        headers,
        contentType: "application/pdf",
        body: document,
      });
      return;
    } else if (u.pathname.endsWith("/approve")) {
      assert.equal(req.headers().authorization, "Bearer ui-fixture-token");
      reviewed = true;
      data = {
        invoice_id: item.id,
        action: "approve",
        reviewed_by: email,
        reviewed_at: now,
        review_notes: "Browser acceptance",
      };
    } else if (u.pathname.startsWith("/api/v1/review/"))
      data = {
        ...item,
        ...(reviewed
          ? { matched_status: "APPROVED", reviewed_by: email, reviewed_at: now }
          : {}),
      };
    else {
      status = 404;
      data = { detail: "Unknown fixture contract" };
    }
    await route.fulfill({
      status,
      headers,
      contentType: "application/json",
      body: JSON.stringify(data),
    });
  });
}
(async () => {
  let server, browser;
  try {
    server = spawn(
      "node",
      [
        "node_modules/vite/bin/vite.js",
        "preview",
        "--host",
        "127.0.0.1",
        "--port",
        "4173",
      ],
      { cwd: path.resolve(__dirname, ".."), stdio: "inherit" },
    );
    for (let i = 0; i < 100; i++) {
      try {
        await fetch(origin);
        break;
      } catch {
        await new Promise((r) => setTimeout(r, 100));
      }
    }
    browser = await chromium.launch({
      ...(process.env.CHROMIUM_PATH
        ? { executablePath: process.env.CHROMIUM_PATH }
        : {}),
      args: ["--no-sandbox", "--disable-dev-shm-usage"],
    });
    const results = [];
    for (const width of [1440, 390]) {
      const page = await browser.newPage({
        viewport: { width, height: 950 },
        acceptDownloads: true,
      });
      const errors = [];
      page.on("pageerror", (e) => errors.push(e.message));
      const stamp = Date.now() + "-" + width,
        email = `browser-${stamp}@example.com`,
        number = "INV-BROWSER-" + stamp,
        document = pdf(number);
      if (fixture) await mockContracts(page, email, number, document);
      await page.goto(origin + "/login");
      await page.getByRole("button", { name: "Sign up here" }).click();
      await page.getByLabel("Name", { exact: true }).fill("Browser Acceptance");
      await page.getByLabel("Email", { exact: true }).fill(email);
      await page
        .getByLabel("Password", { exact: true })
        .fill("BrowserPassword123!");
      await page
        .getByLabel("Confirm password", { exact: true })
        .fill("BrowserPassword123!");
      await page
        .getByRole("button", { name: "Create account", exact: true })
        .click();
      await page.waitForURL("**/login");
      await page.locator("#email").fill(email);
      await page.locator("#password").fill("WrongPassword123!");
      await page.locator("#password").blur();
      await page.getByRole("button", { name: "Sign In", exact: true }).click();
      await page
        .getByText("Invalid email or password", { exact: true })
        .first()
        .waitFor();
      await page.locator("#password").fill("BrowserPassword123!");
      await page.locator("#password").blur();
      await page.getByRole("button", { name: "Sign In", exact: true }).click();
      await page.waitForURL("**/dashboard");
      await page
        .locator("input[type=file]")
        .setInputFiles({
          name: "browser-invoice.pdf",
          mimeType: "application/pdf",
          buffer: document,
        });
      await page.getByRole("button", { name: "Upload PDF" }).click();
      await page.waitForFunction(
        () =>
          document
            .querySelector("[role=status]")
            ?.textContent.includes("processed."),
        {},
        { timeout: 70000 },
      );
      await page.getByRole("link", { name: "Open review queue" }).click();
      const row = page.getByRole("row").filter({ hasText: number });
      await row.getByRole("button", { name: "View", exact: true }).click();
      await page
        .getByRole("heading", { name: "Invoice Review", exact: true })
        .waitFor();
      const downloadPromise = page.waitForEvent("download");
      await page.getByRole("button", { name: "Download source PDF" }).click();
      const dl = await downloadPromise;
      assert.ok(
        fs
          .readFileSync(await dl.path())
          .subarray(0, 5)
          .equals(Buffer.from("%PDF-")),
      );
      await page
        .getByRole("button", { name: "Start Review", exact: true })
        .first()
        .click();
      await page.locator("#reviewed_by").fill(email);
      await page.locator("#review_notes").fill("Browser acceptance");
      await page
        .getByRole("button", { name: "Approve Invoice", exact: true })
        .click();
      await page.getByRole("heading", { name: "Review Complete" }).waitFor();
      await page.reload();
      await page.getByRole("heading", { name: "Review Complete" }).waitFor();
      assert.ok((await page.locator("body").innerText()).includes(email));
      assert.deepEqual(errors, []);
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth > innerWidth + 2,
        ),
        false,
      );
      await page.screenshot({
        path: `/tmp/invoice-review-${width}.png`,
        fullPage: true,
      });
      await page.getByRole("button", { name: "Back to Queue" }).click();
      assert.equal(
        await page.getByRole("row").filter({ hasText: number }).count(),
        0,
      );
      await page.goto(origin + "/dashboard");
      await page.getByRole("button", { name: "Logout", exact: true }).click();
      await page.waitForURL("**/login");
      await page.goto(origin + "/exception");
      await page.waitForURL("**/login");
      results.push({
        width,
        signup: true,
        login: true,
        upload: true,
        review: true,
        sourcePdf: true,
        reload: true,
        logout: true,
        errors,
      });
      await page.close();
    }
    console.log(
      JSON.stringify({
        mode: fixture ? "UI_CONTRACT_FIXTURE" : "REAL_PIPELINE",
        pass: true,
        results,
      }),
    );
  } catch (e) {
    console.error(e.stack);
    process.exitCode = 1;
  } finally {
    if (browser) await browser.close();
    if (server) server.kill();
  }
})();
