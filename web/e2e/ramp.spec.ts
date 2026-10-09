import { test, expect } from "@playwright/test";

test("real ramp rises in physics and appears in saved playback", async ({
  page,
  request,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "全部 21", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "进阶场景 8", exact: true }).click();
  await page
    .getByRole("region", { name: "进阶场景" })
    .getByRole("button", { name: /缓坡上下坡/ })
    .click();
  await expect(page.locator(".world canvas")).toBeVisible();
  const response = page.waitForResponse(
    (r) => r.url().endsWith("/api/runs") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "快速试跑", exact: true }).click();
  const started = await (await response).json();
  await expect(page.getByText("任务完成", { exact: true })).toBeVisible({
    timeout: 20000,
  });
  const saved = await (
    await request.get(`http://127.0.0.1:8765/api/runs/${started.id}`)
  ).json();
  expect(saved.terrain).toHaveLength(2);
  expect(saved.score.success).toBe(true);
  expect(saved.score.falls).toBe(0);
  expect(saved.score.collisions).toBe(0);
  const peak = saved.frames.reduce(
    (best: number, f: { position: number[] }, i: number) =>
      f.position[2] > saved.frames[best].position[2] ? i : best,
    0,
  );
  expect(
    saved.frames[peak].position[2] - saved.frames[0].position[2],
  ).toBeGreaterThan(0.035);
  await page.getByRole("slider", { name: "回放时间轴" }).fill(String(peak));
  await page
    .locator(".stage")
    .screenshot({ path: "test-results/actual-ramp.png" });
  await page.reload();
  await page.getByRole("button", { name: new RegExp(started.id) }).click();
  await expect(
    page.getByRole("heading", { name: "缓坡上下坡", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("combobox", { name: "回放速度" })).toHaveValue(
    "1",
  );
  await page.getByRole("combobox", { name: "回放速度" }).click();
  await page.getByRole("combobox", { name: "回放速度" }).selectOption("4");
  await page.getByRole("button", { name: "播放回放", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "暂停回放", exact: true }),
  ).toBeVisible();
});
