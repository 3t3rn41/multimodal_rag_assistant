import { describe, expect, it, vi } from "vitest";
import { http, invalidateAccountRequests, isCanceledRequest } from "../src/api/http";
import { csrfHeaders } from "../src/api/csrf";

function response(config) {
  return { data: {}, status: 200, statusText: "OK", headers: {}, config };
}

describe("session-bound requests", () => {
  it("decodes the CSRF cookie", () => {
    vi.stubGlobal("document", { cookie: "other=value; mmrag_csrf=session%2Dcsrf" });
    expect(csrfHeaders()).toEqual({ "X-CSRF-Token": "session-csrf" });
  });

  it("does not fabricate a CSRF token without a cookie", () => {
    vi.stubGlobal("document", { cookie: "other=value" });
    expect(csrfHeaders()).toEqual({});
  });

  it("attaches session cookies and CSRF protection to write requests", async () => {
    vi.stubGlobal("document", { cookie: "mmrag_csrf=session-csrf" });
    const result = await http.post("/knowledge", {}, { adapter: async config => response(config) });
    expect(result.config.withCredentials).toBe(true);
    expect(result.config.headers["X-CSRF-Token"]).toBe("session-csrf");
    expect(result.config.headers["X-Requested-With"]).toBe("XMLHttpRequest");
  });

  it("does not attach write-only headers to read requests", async () => {
    vi.stubGlobal("document", { cookie: "mmrag_csrf=session-csrf" });
    const result = await http.get("/knowledge", { adapter: async config => response(config) });
    expect(result.config.headers["X-CSRF-Token"]).toBeUndefined();
    expect(result.config.headers["X-Requested-With"]).toBeUndefined();
  });

  it("rejects a response belonging to the previous account", async () => {
    let resolve;
    const pending = http.get("/knowledge", {
      adapter: config => new Promise(done => { resolve = () => done(response(config)); }),
    });
    await vi.waitFor(() => expect(resolve).toBeTypeOf("function"));
    invalidateAccountRequests();
    resolve();
    await expect(pending).rejects.toSatisfy(isCanceledRequest);
  });
});
