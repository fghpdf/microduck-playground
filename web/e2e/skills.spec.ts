import { test, expect } from "@playwright/test";

test("official football trials move a real ball and pickup carries from A to B and releases", async ({
  page,
  request,
}) => {
  test.setTimeout(90000);
  const scenes = await (
    await request.get("http://127.0.0.1:8765/api/scenarios")
  ).json();
  await page.goto("/");
  for (const id of ["football_left", "football_right", "ground_pick"]) {
    const scene = scenes.find(
      (s: { id: string; task_type: string }) =>
        s.id === id || (id === "ground_pick" && s.task_type === "pickup"),
    );
    expect(scene).toBeTruthy();
    await page
      .getByRole("region", { name: "全部场景" })
      .getByRole("button", { name: new RegExp(scene.name) })
      .click();
    await expect(page.getByRole("button", { name: "开始运行" })).toBeDisabled();
    await expect(
      page.getByText("此技能场景目前仅支持快速试跑。"),
    ).toBeVisible();
    const response = page.waitForResponse(
      (r) => r.url().endsWith("/api/runs") && r.request().method() === "POST",
    );
    await page.getByRole("button", { name: "快速试跑", exact: true }).click();
    const run = await (await response).json();
    await expect(page.getByRole("button", { name: "播放回放" })).toBeEnabled({
      timeout: 60000,
    });
    const saved = await (
      await request.get(`http://127.0.0.1:8765/api/runs/${run.id}`)
    ).json();
    expect(
      saved.frames.some(
        (frame: { objects?: unknown[] }) => frame.objects?.length,
      ),
    ).toBeTruthy();
    if (scene.task_type === "football") {
      expect(saved.goal).toBeTruthy();
      expect(saved.score.success).toBe(true);
      expect(saved.frames.at(-1).t).toBeLessThanOrEqual(3.5);
      expect(saved.score.details.ball_contact).toBe(true);
      expect(saved.score.details.ball_distance).toBeGreaterThan(0.02);
    } else {
      expect(saved.score.success).toBe(true);
      expect(saved.score.details.picked_up).toBe(true);
      expect(saved.score.details.transported).toBe(true);
      expect(saved.score.details.placed).toBe(true);
      expect(saved.score.details.action_completed).toBe(true);
      await expect(page.getByText("任务完成", { exact: true })).toBeVisible();
      await expect(page.getByText(/实际抬升/)).toBeVisible();
      const carrying = saved.frames.findIndex(
        (frame: { pickup?: { phase: string; attached: boolean } }) =>
          frame.pickup?.phase === "transport" && frame.pickup.attached,
      );
      expect(carrying).toBeGreaterThan(0);
      await page
        .getByRole("slider", { name: "回放时间轴" })
        .fill(String(carrying));
      await page.screenshot({ path: "test-results/pickup-carry-preview.png" });
      await page
        .getByRole("slider", { name: "回放时间轴" })
        .fill(String(saved.frames.length - 1));
      await page.screenshot({ path: "test-results/pickup-placed-preview.png" });
    }
    await page.getByRole("slider", { name: "回放时间轴" }).fill("0");
    await page.screenshot({ path: `test-results/${id}-preview.png` });
  }
});
