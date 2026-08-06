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

  it("prefixes relative string URLs during server rendering", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("window", undefined);

    await secureFetch("/api/health");

    expect(fetchMock).toHaveBeenCalledWith("http://poketactics:3000/api/health", {
      credentials: "include",
    });
  });

  it("prefixes relative Request URLs during server rendering", async () => {
    class RelativeRequest {
      url: string;
      constructor(url: string) {
        this.url = url;
      }
    }
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("window", undefined);
    vi.stubGlobal("Request", RelativeRequest);
    const request = new RelativeRequest("/api/health");

    await secureFetch(request as unknown as Request);

    expect(fetchMock.mock.calls[0][0].url).toBe("http://poketactics:3000/api/health");
  });
});
