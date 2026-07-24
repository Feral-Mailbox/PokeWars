import { afterEach, describe, expect, it, vi } from "vitest";
import { secureFetch } from "@/utils/secureFetch";

describe("secureFetch", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("defaults credentials to include and forwards init", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);

    await secureFetch("/api/health", { method: "GET" });

    expect(fetchMock).toHaveBeenCalledWith("/api/health", {
      method: "GET",
      credentials: "include",
    });
  });

  it("preserves explicit credentials", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);

    await secureFetch("/api/health", { credentials: "omit" });

    expect(fetchMock).toHaveBeenCalledWith("/api/health", {
      credentials: "omit",
    });
  });
});
