import { test, expect } from "@playwright/test";
test("language selection translates scenes, controls and persists across refresh", async ({
  page,
}) => {
  await page.goto("/");
  const language = page.getByRole("combobox", {
    name: "Language / 言語 / 언어",
  });
  await language.selectOption("en");
  await expect(
    page.getByRole("button", { name: "Start run", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading",{name:"Walk to the target",exact:true}),
  ).toBeVisible();
  await page.reload();
  await expect(language).toHaveValue("en");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  for (const locale of ["ja", "ko"]) {
    await language.selectOption(locale);
    await expect(page.locator("html")).toHaveAttribute("lang", locale);
    await expect(language).toHaveValue(locale);
  }
  await language.selectOption("zh");
  await expect(
    page.getByRole("button", { name: "开始运行", exact: true }),
  ).toBeVisible();
});
