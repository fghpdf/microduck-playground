import { test, expect } from "@playwright/test";

test("obstacle quick trial saves world geometry and preserves it during playback", async ({
  page,
  request,
}) => {
  test.setTimeout(90000);
  await page.goto("/");
  await expect(page.getByText("21 个场景", { exact: true })).toBeVisible();
  const scenarios = await (
    await request.get("http://127.0.0.1:8765/api/scenarios")
  ).json();
  for (const id of ["detour_left", "detour_right", "slalom"]) {
    const scene = scenarios.find((s: { id: string }) => s.id === id);
    expect(scene.obstacles.length).toBeGreaterThan(0);
    await expect(
      page
        .getByRole("region", { name: "全部场景" })
        .getByRole("button", { name: new RegExp(scene.name) }),
    ).toHaveCount(1);
  }
  const selected = scenarios.find(
    (s: { id: string }) => s.id === "detour_left",
  );
  await page
    .getByRole("region", { name: "全部场景" })
    .getByRole("button", { name: new RegExp(selected.name) })
    .click();
  await expect(page.locator(".world canvas")).toBeVisible();
  const response = page.waitForResponse(
    (r) => r.url().endsWith("/api/runs") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "快速试跑" }).click();
  const started = await (await response).json();
  expect(started.scenario_id).toBe("detour_left");
  await expect(page.getByText("任务完成", { exact: true })).toBeVisible({
    timeout: 60000,
  });
  const saved = await (
    await request.get(`http://127.0.0.1:8765/api/runs/${started.id}`)
  ).json();
  expect(saved.obstacles).toHaveLength(selected.obstacles.length);
  expect(saved.obstacles[0].size).toEqual(selected.obstacles[0].size);
  expect(saved.score.success).toBe(true);
  expect(saved.score.falls).toBe(0);
  expect(saved.score.collisions).toBe(0);
  const slider = page.getByRole("slider", { name: "回放时间轴" });
  await slider.fill(String(saved.frames.length - 1));
  await page.getByRole("button", { name: "播放回放" }).click();
  await page.waitForTimeout(500);
  await page.getByRole("button", { name: "暂停回放" }).click();
  const index = Number(await slider.inputValue());
  expect(index).toBeGreaterThan(0);
  expect(index).toBeLessThan(saved.frames.length - 1);
  await page.reload();
  await page.getByRole("button", { name: new RegExp(started.id) }).click();
  await expect(page.getByText("任务完成", { exact: true })).toBeVisible();
  await expect(slider).toHaveValue("0");
  const reloaded = await (
    await request.get(`http://127.0.0.1:8765/api/runs/${started.id}`)
  ).json();
  expect(reloaded.obstacles).toEqual(saved.obstacles);
  await page.locator(".stage").scrollIntoViewIfNeeded();
  await page.screenshot({
    path: "test-results/obstacle-playback.png",
    fullPage: false,
  });
});
