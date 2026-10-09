import { test, expect } from "@playwright/test";
test("saved physical recordings play at half double and eight times speed", async ({
  page,
  request,
}) => {
  const runs = await (
    await request.get("http://127.0.0.1:8765/api/runs")
  ).json();
  const record = runs.find(
    (r: { score?: { duration: number }; status: string }) =>
      r.score &&
      r.score.duration > 20 &&
      !["starting", "running"].includes(r.status),
  );
  expect(record).toBeTruthy();
  const saved = await (
    await request.get(`http://127.0.0.1:8765/api/runs/${record.id}`)
  ).json();
  await page.goto("/");
  await page.getByRole("button", { name: new RegExp(record.id) }).click();
  const slider = page.getByRole("slider", { name: "回放时间轴" });
  for (const rate of [0.5, 2, 8]) {
    await slider.fill("0");
    await page
      .getByRole("combobox", { name: "回放速度" })
      .selectOption(String(rate));
    await page.getByRole("button", { name: "播放回放", exact: true }).click();
    const start = await page.evaluate(() => performance.now());
    await page.waitForTimeout(700);
    await page.getByRole("button", { name: "暂停回放", exact: true }).click();
    const elapsed =
      ((await page.evaluate(() => performance.now())) - start) / 1000;
    const index = Number(await slider.inputValue());
    expect(saved.frames[index].t).toBeGreaterThan((elapsed - 0.2) * rate);
    expect(saved.frames[index].t).toBeLessThan((elapsed + 0.2) * rate);
    await page.waitForTimeout(100);
    await expect(slider).toHaveValue(String(index));
  }
});
