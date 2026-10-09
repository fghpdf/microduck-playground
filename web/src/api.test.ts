import { it, expect, vi } from "vitest";
import { request } from "./api";
it("passes JSON and reports server errors", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ detail: "无法启动" }),
    }),
  );
  await expect(request("/api/runs", { scenario_id: "a" })).rejects.toThrow(
    "无法启动",
  );
  expect(fetch).toHaveBeenCalledWith(
    "/api/runs",
    expect.objectContaining({ method: "POST" }),
  );
});
it("handles plain errors and invalid error responses", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => {
        throw Error();
      },
    }),
  );
  await expect(request("/api/status")).rejects.toThrow("请求失败（500）");
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue({ ok: false, status: 400, json: async () => ({}) }),
  );
  await expect(request("/api/status")).rejects.toThrow("请求失败（400）");
});
it("returns successful JSON", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({ available: true }) }),
  );
  expect(await request("/api/status")).toEqual({ available: true });
});
