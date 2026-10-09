import { test, expect } from "@playwright/test";

test("fast reference run saves physical frames and replays at normal speed", async ({
  page,
  request,
}) => {
  test.setTimeout(90000);
  await page.goto("/");
  await expect(page.getByRole("button", { name: "快速试跑" })).toBeEnabled();
  await page
    .getByRole("region", { name: "全部场景" })
    .getByRole("button", { name: /短距离停靠/ })
    .click();
  const startedResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/runs") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "快速试跑" }).click();
  const started = await (await startedResponse).json();
  expect(started.mode).toBe("fast_reference");
  await expect(page.getByRole("button", { name: "前进" })).toBeDisabled();
  await expect(page.getByText("任务完成", { exact: true })).toBeVisible({
    timeout: 60000,
  });
  const saved = await (
    await request.get(`http://127.0.0.1:8765/api/runs/${started.id}`)
  ).json();
  expect(saved.score.success).toBe(true);
  expect(saved.score.falls).toBe(0);
  expect(saved.wall_duration).toBeLessThan(saved.frames.at(-1).t);
  await expect(page.getByRole("combobox", { name: "回放速度" })).toHaveValue(
    "1",
  );
  const slider = page.getByRole("slider", { name: "回放时间轴" });
  // Live completion leaves the timeline at the end; Play must restart it.
  await slider.fill(String(saved.frames.length - 1));
  await page.getByRole("button", { name: "播放回放" }).click();
  await page.waitForTimeout(600);
  await page.getByRole("button", { name: "暂停回放" }).click();
  const index = Number(await slider.inputValue());
  const elapsed = saved.frames[index].t - saved.frames[0].t;
  expect(elapsed).toBeGreaterThan(0.3);
  expect(elapsed).toBeLessThan(0.9);
  await page.waitForTimeout(150);
  await expect(slider).toHaveValue(String(index));
  await page.reload();
  await page.getByRole("button", { name: new RegExp(started.id) }).click();
  await expect(page.getByText("任务完成", { exact: true })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "回放速度" })).toHaveValue(
    "1",
  );
  await expect(slider).toHaveValue("0");
});

test("replay speed follows wall time and speed changes preserve position", async ({
  page,
}) => {
  const frames = Array.from({ length: 1001 }, (_, i) => ({
    t: i / 50,
    position: [0, 0, 0.15],
    quaternion: [1, 0, 0, 0],
    joints: [],
    fallen: false,
    collisions: 0,
  }));
  const run = {
    id: "speed-fixture",
    scenario_id: "straight",
    status: "completed",
    frames,
  };
  await page.route("**/api/status", (route) =>
    route.fulfill({ json: { available: true, detail: "ready" } }),
  );
  await page.route("**/api/runs", (route) => route.fulfill({ json: [run] }));
  await page.route("**/api/runs/speed-fixture", (route) =>
    route.fulfill({ json: run }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: /speed-fixture/ }).click();
  const slider = page.getByRole("slider", { name: "回放时间轴" });
  const speed = page.getByRole("combobox", { name: "回放速度" });
  await expect(speed).toBeEnabled();
  await speed.click({ timeout: 3000 });
  await page.keyboard.press("Escape");
  for (const rate of [0.5, 2, 8]) {
    await slider.fill("0");
    await speed.selectOption(String(rate));
    await page.getByRole("button", { name: "播放回放" }).click();
    await page.waitForTimeout(500);
    await page.getByRole("button", { name: "暂停回放" }).click();
    const t = frames[Number(await slider.inputValue())].t;
    expect(t).toBeGreaterThan(0.35 * rate);
    expect(t).toBeLessThan(0.75 * rate);
    const stopped = await slider.inputValue();
    await speed.selectOption("1");
    await page.waitForTimeout(100);
    await expect(slider).toHaveValue(stopped);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await speed.click({ timeout: 3000 });
  await page.keyboard.press("Escape");
  await expect(speed).toBeVisible();
});
