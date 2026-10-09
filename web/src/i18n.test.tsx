import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { I18nProvider, useI18n } from "./i18n";
function Example() {
  const { t, setLocale } = useI18n();
  return (
    <>
      <p>{t("开始运行")}</p>
      <button onClick={() => setLocale("en")}>English</button>
    </>
  );
}
describe("language settings", () => {
  it("switches immediately and persists the choice", () => {
    window.localStorage.clear();
    render(
      <I18nProvider>
        <Example />
      </I18nProvider>,
    );
    expect(screen.getByText("开始运行")).toBeInTheDocument();
    fireEvent.click(screen.getByText("English"));
    expect(screen.getByText("Start run")).toBeInTheDocument();
    expect(window.localStorage.getItem("ducklab.locale")).toBe("en");
    expect(document.documentElement.lang).toBe("en");
    window.localStorage.clear();
  });
});
