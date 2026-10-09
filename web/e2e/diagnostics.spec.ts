import { test, expect } from "@playwright/test";
test("official diagnostics persist and remain visible in historical playback", async ({
  page,
  request,
}) => {
  const status = await (
    await request.get("http://127.0.0.1:8765/api/status")
  ).json();
  expect(status.available, status.detail).toBe(true);
  await page.goto("/");
  await page.getByRole("button", { name: "开始运行" }).click();
  await expect(page.getByRole("button", { name: "前进" })).toBeEnabled({
    timeout: 90000,
  });
  await page.keyboard.down("w");
  await page.waitForTimeout(1300);
  await page.keyboard.up("w");
  await page.getByRole("button", { name: "停止并保存" }).click();
  await expect(page.getByRole("button", { name: "开始运行" })).toBeEnabled({
    timeout: 30000,
  });
  const runs = await (
    await request.get("http://127.0.0.1:8765/api/runs")
  ).json();
  const run = await (
    await request.get(`http://127.0.0.1:8765/api/runs/${runs[0].id}`)
  ).json();
  expect(run.diagnostics.commands.length).toBeGreaterThan(2);
  expect(
    run.diagnostics.commands.some(
      (c: { accepted: boolean | null; vx: number }) =>
        c.accepted === true && c.vx === 0.3,
    ),
  ).toBe(true);
  expect(run.diagnostics.health.length).toBeGreaterThan(0);
  expect(
    run.diagnostics.health.some((h: { result: unknown }) => h.result !== null),
  ).toBe(true);
  const diagnostic = page.getByRole("region", { name: "运行诊断" });
  await expect(diagnostic).toBeVisible();
  await expect(diagnostic.getByText(/次 · .*次失败/)).toBeVisible();
  await expect(diagnostic.getByText(/Hz/)).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: new RegExp(run.id) }).click();
  await expect(page.getByRole("region", { name: "运行诊断" })).toBeVisible();
  const failures = run.diagnostics.commands.filter(
    (c: { accepted: boolean | null; error: string | null }) =>
      c.accepted === false || !!c.error,
  ).length;
  await expect(
    page.getByText(
      `${run.diagnostics.commands.length} 次 · ${failures} 次失败`,
      { exact: true },
    ),
  ).toBeVisible();
  await expect(page.getByRole("slider", { name: "回放时间轴" })).toBeEnabled();
  await page.screenshot({
    path: "test-results/diagnostics.png",
    fullPage: true,
  });
});
