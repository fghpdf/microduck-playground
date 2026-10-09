import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import Diagnostics from "./Diagnostics";
import { fireEvent } from "@testing-library/react";
import { I18nProvider, useI18n } from "./i18n";
describe("run diagnostics", () => {
  it("handles old runs without telemetry", () => {
    render(<Diagnostics />);
    expect(screen.getByText("此记录没有诊断数据")).toBeInTheDocument();
  });
});
it("shows measured cadence, rejected commands, and real latency", () => {
  render(
    <Diagnostics
      data={{
        commands: [
          {
            sent_at: 1,
            duration_ms: 12,
            vx: 0.2,
            vyaw: 0,
            accepted: true,
            error: null,
          },
          {
            sent_at: 2,
            duration_ms: 84.2,
            vx: 0,
            vyaw: 0,
            accepted: false,
            error: null,
          },
        ],
        health: [
          {
            sampled_at: 2,
            duration_ms: 8,
            result: {
              healthy: true,
              control_loop: { target_hz: 50, achieved_hz: 31.6 },
            },
            error: null,
          },
        ],
      }}
    />,
  );
  expect(screen.getByText("31.6 / 50 Hz")).toBeInTheDocument();
  expect(screen.getByText("2 次 · 1 次失败")).toBeInTheDocument();
  expect(screen.getByText("84.2 ms")).toBeInTheDocument();
  expect(screen.getByText(/控制频率偏低/)).toBeInTheDocument();
});
it("does not turn unknown frequency or failed health request into zero or ready", () => {
  render(
    <Diagnostics
      data={{
        commands: [
          {
            sent_at: 1,
            duration_ms: 750,
            vx: 0.2,
            vyaw: 0,
            accepted: null,
            error: "超时",
          },
        ],
        health: [
          {
            sampled_at: 1,
            duration_ms: 3,
            result: { control_loop: { target_hz: 50, achieved_hz: null } },
            error: null,
          },
          {
            sampled_at: 2,
            duration_ms: 750,
            result: null,
            error: "状态查询超时",
          },
        ],
      }}
    />,
  );
  expect(screen.getByText("未知 / 50 Hz")).toBeInTheDocument();
  expect(screen.getByText("1 次 · 1 次失败")).toBeInTheDocument();
  expect(screen.getByText("状态查询超时")).toBeInTheDocument();
});
it("displays healthy timing without slow warning and pending commands are not failures", () => {
  render(
    <Diagnostics
      data={{
        commands: [
          {
            sent_at: 1,
            duration_ms: 3,
            vx: 0,
            vyaw: 0,
            accepted: null,
            error: null,
          },
        ],
        health: [
          {
            sampled_at: 1,
            duration_ms: 3,
            result: { control_loop: { target_hz: 50, achieved_hz: 49.8 } },
            error: null,
          },
        ],
      }}
    />,
  );
  expect(screen.queryByText(/控制频率偏低/)).not.toBeInTheDocument();
  expect(screen.getByText("1 次 · 0 次失败")).toBeInTheDocument();
});
it("handles empty diagnostics without fabricating latency", () => {
  render(<Diagnostics data={{ commands: [], health: [] }} />);
  expect(screen.getByText("尚无指令")).toBeInTheDocument();
  expect(screen.getByText("未知 / 50 Hz")).toBeInTheDocument();
});

function DiagnosticLanguageControl() {
  const { setLocale } = useI18n();
  return <button onClick={() => setLocale("en")}>English</button>;
}
it("updates diagnostics when language changes without losing measured values", () => {
  window.localStorage.clear();
  render(
    <I18nProvider>
      <DiagnosticLanguageControl />
      <Diagnostics data={{ commands: [], health: [] }} />
    </I18nProvider>,
  );
  expect(screen.getByText("运行诊断")).toBeInTheDocument();
  fireEvent.click(screen.getByText("English"));
  expect(screen.queryByText("运行诊断")).not.toBeInTheDocument();
  expect(screen.getByText(/50 Hz/)).toBeInTheDocument();
  window.localStorage.clear();
});
