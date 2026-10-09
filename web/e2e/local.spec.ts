import { test, expect } from "@playwright/test";
test("official local simulation starts, moves, stops and replays", async ({
  page,
  request,
}, testInfo) => {
  const commands: { time: number; body: unknown; status: number }[] = [];
  page.on("response", async (response) => {
    if (response.url().endsWith("/api/control"))
      commands.push({
        time: Date.now(),
        body: response.request().postDataJSON(),
        status: response.status(),
      });
  });
  await page.addInitScript(() => {
    (window as unknown as { controlEvents: string[] }).controlEvents = [];
    ["keydown", "keyup", "blur"].forEach((type) =>
      window.addEventListener(type, (e) => {
        (window as unknown as { controlEvents: string[] }).controlEvents.push(
          `${Date.now()} ${type} ${(e as KeyboardEvent).key ?? ""}`,
        );
      }),
    );
  });
  const status = await request.get("http://127.0.0.1:8765/api/status");
  expect(status.ok()).toBeTruthy();
  const body = await status.json();
  expect(body.available, body.detail).toBeTruthy();
  await page.goto("/");
  await expect(page.getByRole("button", { name: "开始运行" })).toBeEnabled();
  await page.getByRole("button", { name: "开始运行" }).click();
  await expect(page.getByRole("button", { name: "前进" })).toBeEnabled({
    timeout: 90000,
  });
  await page.keyboard.down("w");
  await page.waitForTimeout(2500);
  await page.keyboard.up("w");
  await testInfo.attach("control-transport", {
    body: JSON.stringify(
      {
        commands,
        events: await page.evaluate(
          () =>
            (window as unknown as { controlEvents: string[] }).controlEvents,
        ),
      },
      null,
      2,
    ),
    contentType: "application/json",
  });
  expect(
    commands.filter(
      (c) => (c.body as { vx: number }).vx === 0.3 && c.status === 200,
    ).length,
  ).toBeGreaterThan(10);
  await page.getByRole("button", { name: "停止并保存" }).click();
  await expect(page.getByRole("button", { name: "播放回放" })).toBeEnabled({
    timeout: 30000,
  });
  const runs = await (
    await request.get("http://127.0.0.1:8765/api/runs")
  ).json();
  const run = await (
    await request.get(`http://127.0.0.1:8765/api/runs/${runs[0].id}`)
  ).json();
  expect(run.frames.length).toBeGreaterThan(2);
  expect(run.score).not.toBeNull();
  expect(run.score.falls).toBe(0);
  expect(run.score.completion).toBeGreaterThan(0);
  expect(run.diagnostics.commands.length).toBeGreaterThan(10);
  expect(run.diagnostics.health.length).toBeGreaterThan(0);
  await expect(page.getByRole("region", { name: "运行诊断" })).toBeVisible();
  expect(typeof run.score.success).toBe("boolean");
  await expect(
    page.getByText(run.score.success ? "任务完成" : "任务未完成", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText(`完成度 ${Math.round(run.score.completion)}%`, {
      exact: true,
    }),
  ).toBeVisible();
  const first = run.frames[0].position;
  expect(
    run.frames.some(
      (f: { position: number[] }) =>
        Math.hypot(f.position[0] - first[0], f.position[1] - first[1]) > 0.1,
    ),
  ).toBeTruthy();
  await page.getByRole("slider", { name: "回放时间轴" }).fill("0");
  await page.getByRole("button", { name: "播放回放" }).click();
  await expect(page.getByRole("button", { name: "暂停回放" })).toBeVisible();
  await page.getByRole("button", { name: "暂停回放" }).click();
  await page.getByRole("slider", { name: "回放时间轴" }).fill("0");
  await expect(page.getByRole("slider", { name: "回放时间轴" })).toHaveValue(
    "0",
  );
  await page
    .getByRole("slider", { name: "回放时间轴" })
    .fill(String(Math.floor(run.frames.length / 2)));
  await page.screenshot({
    path: "test-results/local-simulation.png",
    fullPage: true,
  });
});
