import { test, expect } from "@playwright/test";

test("difficulty groups select real tasks and historical playback remains discoverable", async ({
  page,
  request,
}) => {
  test.setTimeout(90000);
  const scenes = await (
    await request.get("http://127.0.0.1:8765/api/scenarios")
  ).json();
  expect(scenes).toHaveLength(21);
  await page.goto("/");
  for (const [difficulty, label] of [
    ["simple", "简单场景"],
    ["advanced", "进阶场景"],
    ["complex", "复杂场景"],
  ]) {
    const count = scenes.filter(
      (s: { difficulty: string }) => s.difficulty === difficulty,
    ).length;
    await page
      .getByRole("button", { name: `${label} ${count}`, exact: true })
      .click();
    await expect(
      page.getByRole("region", { name: label }).getByRole("button"),
    ).toHaveCount(count);
  }
  let lastId = "";
  for (const [difficulty, label, id] of [
    ["advanced", "进阶场景", "corridor"],
    ["complex", "复杂场景", "diagonal_barrier"],
  ]) {
    const count = scenes.filter(
      (s: { difficulty: string }) => s.difficulty === difficulty,
    ).length;
    const scene = scenes.find((s: { id: string }) => s.id === id);
    await page
      .getByRole("button", { name: `${label} ${count}`, exact: true })
      .click();
    await page
      .getByRole("region", { name: label })
      .getByRole("button", { name: new RegExp(scene.name) })
      .click();
    const response = page.waitForResponse(
      (r) => r.url().endsWith("/api/runs") && r.request().method() === "POST",
    );
    await page.getByRole("button", { name: "快速试跑", exact: true }).click();
    const run = await (await response).json();
    lastId = run.id;
    expect(run.scenario_id).toBe(id);
    await expect(page.getByText("任务完成", { exact: true })).toBeVisible({
      timeout: 60000,
    });
    const saved = await (
      await request.get(`http://127.0.0.1:8765/api/runs/${run.id}`)
    ).json();
    expect(saved.score.success).toBe(true);
    expect(saved.score.falls).toBe(0);
    expect(saved.score.collisions).toBe(0);
  }
  await page.getByRole("button", { name: "简单场景 8", exact: true }).click();
  await expect(page.getByRole("slider")).toBeDisabled();
  await page.getByRole("button", { name: new RegExp(lastId) }).click();
  await expect(
    page.getByRole("button", { name: "全部 21", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(
    page.getByRole("region", { name: "全部场景" }).getByRole("button", {
      name: new RegExp(
        scenes.find((s: { id: string }) => s.id === "diagonal_barrier").name,
      ),
    }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("slider")).toBeEnabled();
  await page.getByRole("button", { name: "复杂场景 5", exact: true }).click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: "test-results/scene-categories.png" });
});
