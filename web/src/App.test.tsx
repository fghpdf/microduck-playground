import {
  render,
  screen,
  fireEvent,
  waitFor,
  within,
} from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import App from "./App";
vi.mock("./World", () => ({
  default: ({
    target,
    obstacles,
  }: {
    target?: [number, number];
    obstacles?: unknown[];
  }) => (
    <div
      data-testid="world"
      data-target={JSON.stringify(target)}
      data-obstacles={JSON.stringify(obstacles)}
    >
      三维场景
    </div>
  ),
}));
const scenarios = [
  {
    id: "reach",
    name: "走到目标点",
    description: "到达标记",
    target: [1, 0],
    duration: 30,
  },
  {
    id: "ball",
    name: "找球",
    description: "寻找球",
    target: [2, 0],
    duration: 60,
  },
];
beforeEach(() =>
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string) => ({
      ok: true,
      json: async () =>
        input === "/api/status"
          ? { available: false, detail: "需要安装官方依赖" }
          : input === "/api/scenarios"
            ? scenarios
            : [],
    })),
  ),
);
describe("local simulation", () => {
  it("blocks starting when official backend is unavailable", async () => {
    render(<App />);
    expect(await screen.findByText("需要安装官方依赖")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "开始运行" })).toBeDisabled();
  });
  it("allows choosing a scenario without inventing a result", async () => {
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /找球/ }));
    expect(screen.getByRole("button", { name: /找球/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByText("等待第一次运行")).toBeInTheDocument();
  });
  it("loads recorded frames and score from the service", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string) => ({
        ok: true,
        json: async () =>
          input === "/api/status"
            ? { available: true, detail: "就绪" }
            : input === "/api/scenarios"
              ? scenarios
              : input === "/api/runs"
                ? [{ id: "abc", scenario_id: "reach", status: "completed" }]
                : {
                    id: "abc",
                    scenario_id: "reach",
                    status: "completed",
                    frames: [
                      {
                        t: 0,
                        position: [0, 0, 0],
                        quaternion: [1, 0, 0, 0],
                        joints: [],
                      },
                      {
                        t: 2,
                        position: [1, 0, 0],
                        quaternion: [1, 0, 0, 0],
                        joints: [],
                      },
                    ],
                    events: [],
                    score: {
                      success: true,
                      completion: 100,
                      duration: 2,
                      falls: 0,
                      collisions: 0,
                    },
                  },
      })),
    );
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /abc/ }));
    await waitFor(() =>
      expect(screen.getByText("任务完成")).toBeInTheDocument(),
    );
    expect(screen.getByRole("slider", { name: "回放时间轴" })).toHaveAttribute(
      "max",
      "1",
    );
  });
});

it("polls starting runs and locks scene selection until ready", async () => {
  let details = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init?: RequestInit) => ({
      ok: true,
      json: async () =>
        input === "/api/status"
          ? { available: true, detail: "就绪" }
          : input === "/api/scenarios"
            ? scenarios
            : input === "/api/runs"
              ? init
                ? {
                    id: "pending",
                    scenario_id: "reach",
                    status: "starting",
                    frames: [],
                  }
                : []
              : {
                  id: "pending",
                  scenario_id: "reach",
                  status: ++details ? "running" : "starting",
                  frames: [],
                  events: [],
                  score: null,
                },
    })),
  );
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "开始运行" }));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "开始运行" })).toBeDisabled(),
  );
  expect(screen.getByRole("button", { name: /找球/ })).toBeDisabled();
  expect(screen.getByRole("button", { name: "停止并保存" })).not.toBeDisabled();
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "前进" })).not.toBeDisabled(),
  );
});

it("restores the active official session on refresh", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string) => ({
      ok: true,
      json: async () =>
        input === "/api/status"
          ? { available: true, detail: "就绪", active_run: "restored" }
          : input === "/api/scenarios"
            ? scenarios
            : input === "/api/runs"
              ? []
              : {
                  id: "restored",
                  scenario_id: "ball",
                  status: "running",
                  frames: [],
                  events: [],
                  score: null,
                },
    })),
  );
  render(<App />);
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "前进" })).toBeEnabled(),
  );
  expect(screen.getByRole("button", { name: /找球/ })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(screen.getByRole("button", { name: "开始运行" })).toBeDisabled();
});

const recordedFrames = [0, 0.02, 0.04].map((t) => ({
  t,
  position: [t, 0, 0.12],
  quaternion: [1, 0, 0, 0],
  joints: [],
}));
function serve(handler: (url: string, init?: RequestInit) => unknown) {
  const mock = vi.fn(async (url: string, init?: RequestInit) => {
    const value = handler(url, init);
    if (value instanceof Error) throw value;
    return { ok: true, json: async () => value };
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}
function initial(url: string) {
  return url === "/api/status"
    ? { available: true, detail: "就绪" }
    : url === "/api/scenarios"
      ? scenarios
      : [];
}
it("reports connection failure and keeps start disabled", async () => {
  serve(() => new Error("服务离线"));
  render(<App />);
  expect(await screen.findByRole("alert")).toHaveTextContent("服务离线");
  expect(screen.getByRole("button", { name: "开始运行" })).toBeDisabled();
});
it("reports launch failure and permits retry", async () => {
  serve((url, init) => (init ? new Error("策略无法载入") : initial(url)));
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "开始运行" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("策略无法载入");
  expect(screen.getByRole("button", { name: "开始运行" })).toBeEnabled();
});
it("reports missing historical data", async () => {
  serve((url) =>
    url === "/api/runs"
      ? [{ id: "missing", scenario_id: "reach", status: "failed" }]
      : url.includes("missing")
        ? new Error("记录不存在")
        : initial(url),
  );
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /missing/ }));
  expect(await screen.findByRole("alert")).toHaveTextContent("记录不存在");
});
it("shows execution failure after polling and unlocks start", async () => {
  serve((url, init) =>
    url === "/api/runs"
      ? init
        ? { id: "failed", scenario_id: "reach", status: "starting" }
        : []
      : url.includes("failed")
        ? {
            id: "failed",
            scenario_id: "reach",
            status: "failed",
            frames: [],
            error: "无法站稳",
            score: null,
          }
        : initial(url),
  );
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "开始运行" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("无法站稳");
  expect(screen.getByRole("button", { name: "开始运行" })).toBeEnabled();
});
it("sends movement only during running and sends zero on release and blur", async () => {
  const run = {
    id: "control",
    scenario_id: "reach",
    status: "running",
    frames: recordedFrames,
  };
  const mock = serve((url, init) =>
    url === "/api/runs"
      ? init
        ? run
        : []
      : url.includes("control")
        ? run
        : initial(url),
  );
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "开始运行" }));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "前进" })).toBeEnabled(),
  );
  fireEvent.keyDown(window, { key: "w" });
  await waitFor(() =>
    expect(mock).toHaveBeenCalledWith(
      "/api/control",
      expect.objectContaining({ body: '{"vx":0.3,"vyaw":0}' }),
    ),
  );
  fireEvent.keyUp(window, { key: "w" });
  await waitFor(() =>
    expect(mock).toHaveBeenCalledWith(
      "/api/control",
      expect.objectContaining({ body: '{"vx":0,"vyaw":0}' }),
    ),
  );
  fireEvent.keyDown(window, { key: "a" });
  fireEvent.blur(window);
  fireEvent.keyDown(window, { key: "d", repeat: true });
  const forward = screen.getByRole("button", { name: "前进" });
  forward.setPointerCapture = vi.fn();
  fireEvent.pointerDown(forward, { pointerId: 1 });
  fireEvent.pointerCancel(forward);
});
it("stops an active run, exposes genuine failure score and supports playback seeking", async () => {
  const running = {
    id: "stop",
    scenario_id: "reach",
    status: "running",
    frames: recordedFrames,
  };
  const stopped = {
    ...running,
    status: "stopped",
    score: {
      success: false,
      completion: 34,
      duration: 0.04,
      falls: 1,
      collisions: 2,
    },
  };
  serve((url, init) =>
    url === "/api/runs"
      ? init
        ? running
        : [stopped]
      : url.endsWith("/stop/stop")
        ? stopped
        : url === "/api/runs/stop"
          ? running
          : initial(url),
  );
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "开始运行" }));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "停止并保存" })).toBeEnabled(),
  );
  fireEvent.click(screen.getByRole("button", { name: "停止并保存" }));
  expect(await screen.findByText("任务未完成")).toBeInTheDocument();
  expect(screen.getByText("完成度 34%")).toBeInTheDocument();
  fireEvent.change(screen.getByRole("slider", { name: "回放时间轴" }), {
    target: { value: "0" },
  });
  fireEvent.click(screen.getByRole("button", { name: "下一帧" }));
  expect(screen.getByRole("slider", { name: "回放时间轴" })).toHaveValue("1");
  fireEvent.click(screen.getByRole("button", { name: "上一帧" }));
  expect(screen.getByRole("slider", { name: "回放时间轴" })).toHaveValue("0");
  fireEvent.click(screen.getByRole("button", { name: "播放回放" }));
  await waitFor(() =>
    expect(screen.getByRole("slider", { name: "回放时间轴" })).toHaveValue("2"),
  );
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "播放回放" }),
    ).toBeInTheDocument(),
  );
});
it("reports stop and movement transport failures", async () => {
  serve((url, init) =>
    url === "/api/runs"
      ? init
        ? { id: "network", scenario_id: "reach", status: "running", frames: [] }
        : []
      : url === "/api/control"
        ? new Error("控制失败")
        : url.endsWith("/stop")
          ? new Error("停止失败")
          : initial(url),
  );
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "开始运行" }));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "前进" })).toBeEnabled(),
  );
  fireEvent.keyDown(window, { key: "s" });
  expect(await screen.findByRole("alert")).toHaveTextContent("控制失败");
  fireEvent.keyUp(window);
  fireEvent.click(screen.getByRole("button", { name: "停止并保存" }));
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("停止失败"),
  );
});

it("keeps a held command alive across live state polls", async () => {
  const running = {
    id: "steady",
    scenario_id: "reach",
    status: "running",
    frames: recordedFrames,
  };
  const transport = serve((url, init) =>
    url === "/api/runs"
      ? init
        ? running
        : []
      : url === "/api/runs/steady"
        ? {
            ...running,
            frames: [...recordedFrames, { ...recordedFrames[0], t: 0.08 }],
          }
        : initial(url),
  );
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "开始运行" }));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "前进" })).toBeEnabled(),
  );
  fireEvent.keyDown(window, { key: "w" });
  await waitFor(() =>
    expect(
      transport.mock.calls.filter(
        ([url, init]) =>
          url === "/api/control" && init?.body === '{"vx":0.3,"vyaw":0}',
      ).length,
    ).toBeGreaterThanOrEqual(4),
  );
  expect(transport.mock.calls.some(([url]) => url === "/api/runs/steady")).toBe(
    true,
  );
  expect(
    transport.mock.calls.some(
      ([url, init]) =>
        url === "/api/control" && init?.body === '{"vx":0,"vyaw":0}',
    ),
  ).toBe(false);
  fireEvent.keyUp(window, { key: "w" });
  await waitFor(() =>
    expect(
      transport.mock.calls.some(
        ([url, init]) =>
          url === "/api/control" && init?.body === '{"vx":0,"vyaw":0}',
      ),
    ).toBe(true),
  );
});

it("turns while moving forward and S stops without requesting reverse", async () => {
  const running = {
    id: "turn",
    scenario_id: "reach",
    status: "running",
    frames: recordedFrames,
  };
  const transport = serve((url, init) =>
    url === "/api/runs"
      ? init
        ? running
        : []
      : url === "/api/runs/turn"
        ? running
        : initial(url),
  );
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "开始运行" }));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "前进" })).toBeEnabled(),
  );
  fireEvent.keyDown(window, { key: "a" });
  await waitFor(() =>
    expect(transport).toHaveBeenCalledWith(
      "/api/control",
      expect.objectContaining({ body: '{"vx":0.3,"vyaw":0.5}' }),
    ),
  );
  fireEvent.keyUp(window, { key: "a" });
  fireEvent.keyDown(window, { key: "d" });
  await waitFor(() =>
    expect(transport).toHaveBeenCalledWith(
      "/api/control",
      expect.objectContaining({ body: '{"vx":0.3,"vyaw":-0.5}' }),
    ),
  );
  fireEvent.keyUp(window, { key: "d" });
  fireEvent.keyDown(window, { key: "s" });
  await waitFor(() =>
    expect(transport).toHaveBeenCalledWith(
      "/api/control",
      expect.objectContaining({ body: '{"vx":0,"vyaw":0}' }),
    ),
  );
  fireEvent.keyUp(window, { key: "s" });
  expect(
    transport.mock.calls.some(
      ([url, init]) =>
        url === "/api/control" && JSON.parse(String(init?.body)).vx < 0,
    ),
  ).toBe(false);
  expect(
    screen.getByText("转弯时会向前行走，S 停车 · 松开即停止"),
  ).toBeInTheDocument();
});

it("renders the translated official target when the standing run becomes ready", async () => {
  const transport = serve((url, init) =>
    url === "/api/runs"
      ? init
        ? { id: "pose", scenario_id: "reach", status: "starting" }
        : []
      : url === "/api/runs/pose"
        ? {
            id: "pose",
            scenario_id: "reach",
            status: "running",
            target: [-0.25, 0.72],
            frames: recordedFrames,
          }
        : initial(url),
  );
  render(<App />);
  await screen.findByRole("button", { name: "开始运行" });
  expect(screen.getByTestId("world")).toHaveAttribute("data-target", "[1,0]");
  fireEvent.click(screen.getByRole("button", { name: "开始运行" }));
  await waitFor(() =>
    expect(screen.getByTestId("world")).toHaveAttribute(
      "data-target",
      "[-0.25,0.72]",
    ),
  );
  expect(transport).toHaveBeenCalledWith("/api/runs/pose", undefined);
});

it("renders all eight scenes and starts the newly selected right turn with its real target", async () => {
  const expanded = [
    ...scenarios,
    {
      id: "stop",
      name: "短距离停靠",
      description: "向前40厘米",
      target: [0.4, 0],
      duration: 20,
    },
    {
      id: "far",
      name: "远距离到达",
      description: "向前1.5米",
      target: [1.5, 0],
      duration: 40,
    },
    {
      id: "right_turn",
      name: "右转到达",
      description: "走向右前方",
      target: [0.65, -0.65],
      duration: 30,
    },
    {
      id: "left_diagonal",
      name: "左斜向到达",
      description: "走向左前方",
      target: [0.9, 0.35],
      duration: 30,
    },
    {
      id: "right_diagonal",
      name: "右斜向到达",
      description: "走向右前方",
      target: [0.9, -0.35],
      duration: 30,
    },
    {
      id: "large_left",
      name: "大角度左转",
      description: "走向左前方",
      target: [0.35, 0.9],
      duration: 40,
    },
  ];
  const transport = serve((url, init) =>
    url === "/api/scenarios"
      ? expanded
      : url === "/api/runs"
        ? init
          ? { id: "right-run", scenario_id: "right_turn", status: "starting" }
          : []
        : initial(url),
  );
  render(<App />);
  expect(await screen.findByText("8 个场景")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /大角度左转/ })).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: /右转到达/ }));
  expect(screen.getByTestId("world")).toHaveAttribute(
    "data-target",
    "[0.65,-0.65]",
  );
  fireEvent.click(screen.getByRole("button", { name: "开始运行" }));
  await waitFor(() =>
    expect(transport).toHaveBeenCalledWith(
      "/api/runs",
      expect.objectContaining({ body: '{"scenario_id":"right_turn"}' }),
    ),
  );
  expect(screen.getByRole("region", { name: "全部场景" })).toBeInTheDocument();
});

it("starts an automatic fast reference run and blocks manual control", async () => {
  const running = {
    id: "fast",
    scenario_id: "reach",
    mode: "fast_reference",
    status: "running",
    frames: recordedFrames,
  };
  const transport = serve((url, init) =>
    url === "/api/runs"
      ? init
        ? running
        : []
      : url === "/api/runs/fast"
        ? running
        : initial(url),
  );
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "快速试跑" }));
  await waitFor(() =>
    expect(screen.getByText("● 快速计算")).toBeInTheDocument(),
  );
  expect(transport).toHaveBeenCalledWith(
    "/api/runs",
    expect.objectContaining({
      body: '{"scenario_id":"reach","mode":"fast_reference"}',
    }),
  );
  expect(screen.getByRole("button", { name: "前进" })).toBeDisabled();
  fireEvent.keyDown(window, { key: "w" });
  fireEvent.keyUp(window, { key: "w" });
  expect(transport.mock.calls.some(([url]) => url === "/api/control")).toBe(
    false,
  );
});

it("plays fast results at simulated time and shows separate computation duration", async () => {
  const fast = {
    id: "fast-record",
    scenario_id: "reach",
    mode: "fast_reference",
    status: "completed",
    wall_duration: 0.01,
    frames: [recordedFrames[0], { ...recordedFrames[1], t: 0.4 }],
    score: {
      success: true,
      completion: 100,
      duration: 0.4,
      falls: 0,
      collisions: 0,
    },
  };
  serve((url) =>
    url === "/api/runs"
      ? [fast]
      : url.includes("fast-record")
        ? fast
        : initial(url),
  );
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /fast-record/ }));
  expect(await screen.findByText("计算耗时 0.0s")).toBeInTheDocument();
  expect(screen.getByText("仿真时长 0.4s")).toBeInTheDocument();
  expect(screen.getByText("1× 正常速度")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "播放回放" }));
  await new Promise((resolve) => setTimeout(resolve, 80));
  expect(screen.getByRole("slider", { name: "回放时间轴" })).toHaveValue("0");
  await waitFor(() =>
    expect(screen.getByRole("slider", { name: "回放时间轴" })).toHaveValue("1"),
  );
});

it("restarts playback from the beginning when play is clicked at the final frame", async () => {
  const saved = {
    id: "ended",
    scenario_id: "reach",
    status: "completed",
    frames: [recordedFrames[0], { ...recordedFrames[1], t: 0.3 }],
  };
  serve((url) =>
    url === "/api/runs"
      ? [saved]
      : url.includes("ended")
        ? saved
        : initial(url),
  );
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /ended/ }));
  await waitFor(() =>
    expect(screen.getByRole("slider", { name: "回放时间轴" })).toHaveAttribute(
      "max",
      "1",
    ),
  );
  fireEvent.change(screen.getByRole("slider", { name: "回放时间轴" }), {
    target: { value: "1" },
  });
  fireEvent.click(screen.getByRole("button", { name: "播放回放" }));
  expect(screen.getByRole("slider", { name: "回放时间轴" })).toHaveValue("0");
  expect(screen.getByRole("button", { name: "暂停回放" })).toBeInTheDocument();
  await waitFor(() =>
    expect(screen.getByRole("slider", { name: "回放时间轴" })).toHaveValue("1"),
  );
});

const previewObstacles = [
  { position: [0.5, 0, 0.15], size: [0.2, 0.6, 0.3], yaw: 0 },
];
it("previews scene obstacles and uses saved world geometry for playback", async () => {
  const savedObstacles = [
    { position: [1, -0.4, 0.15], size: [0.2, 0.6, 0.3], yaw: 0.8 },
  ];
  serve((url) =>
    url === "/api/scenarios"
      ? [{ ...scenarios[0], obstacles: previewObstacles }, scenarios[1]]
      : url === "/api/runs"
        ? [
            {
              id: "obstacle-history",
              scenario_id: "reach",
              status: "completed",
            },
          ]
        : url.includes("obstacle-history")
          ? {
              id: "obstacle-history",
              scenario_id: "reach",
              status: "completed",
              obstacles: savedObstacles,
              frames: recordedFrames,
            }
          : initial(url),
  );
  render(<App />);
  await screen.findByRole("region", { name: "全部场景" });
  expect(screen.getByTestId("world")).toHaveAttribute(
    "data-obstacles",
    JSON.stringify(previewObstacles),
  );
  fireEvent.click(screen.getByRole("button", { name: /obstacle-history/ }));
  await waitFor(() =>
    expect(screen.getByTestId("world")).toHaveAttribute(
      "data-obstacles",
      JSON.stringify(savedObstacles),
    ),
  );
});
it("does not borrow current scene obstacles for older obstacle-free recordings", async () => {
  serve((url) =>
    url === "/api/scenarios"
      ? [{ ...scenarios[0], obstacles: previewObstacles }]
      : url === "/api/runs"
        ? [{ id: "old-clear", scenario_id: "reach", status: "completed" }]
        : url.includes("old-clear")
          ? {
              id: "old-clear",
              scenario_id: "reach",
              status: "completed",
              frames: recordedFrames,
            }
          : initial(url),
  );
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /old-clear/ }));
  await waitFor(() =>
    expect(screen.getByTestId("world")).toHaveAttribute("data-obstacles", "[]"),
  );
});

const groupedScenes = [
  { ...scenarios[0], difficulty: "simple", category: "navigation" },
  { ...scenarios[1], difficulty: "advanced", category: "navigation" },
  {
    ...scenarios[0],
    id: "maze",
    name: "交错通道",
    difficulty: "complex",
    category: "obstacle",
    target: [3, 1],
  },
];
function grouped(url: string) {
  return url === "/api/scenarios" ? groupedScenes : initial(url);
}
it("filters difficulty with counts and chooses a matching preview", async () => {
  serve(grouped);
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "复杂场景 1" }));
  expect(
    screen.queryByRole("button", { name: /走到目标点/ }),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /交错通道/ })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(screen.getByTestId("world")).toHaveAttribute("data-target", "[3,1]");
  expect(screen.getByText("障碍避让")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "全部 3" }));
  expect(screen.getByRole("button", { name: /交错通道/ })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});
it("synchronizes historical scenario and clears playback when filtering it away", async () => {
  serve((url) =>
    url === "/api/runs"
      ? [{ id: "maze-history", scenario_id: "maze", status: "completed" }]
      : url.includes("maze-history")
        ? {
            id: "maze-history",
            scenario_id: "maze",
            status: "completed",
            frames: recordedFrames,
          }
        : grouped(url),
  );
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "简单场景 1" }));
  fireEvent.click(screen.getByRole("button", { name: /maze-history/ }));
  await waitFor(() =>
    expect(
      within(screen.getByRole("region", { name: "全部场景" })).getByRole(
        "button",
        { name: /交错通道/ },
      ),
    ).toHaveAttribute("aria-pressed", "true"),
  );
  expect(screen.getByRole("button", { name: "全部 3" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  fireEvent.click(screen.getByRole("button", { name: "简单场景 1" }));
  expect(screen.getByRole("slider", { name: "回放时间轴" })).toBeDisabled();
  expect(screen.getByTestId("world")).toHaveAttribute("data-target", "[1,0]");
});
it("locks category filters and preserves restored running scene", async () => {
  serve((url) =>
    url === "/api/status"
      ? { available: true, detail: "就绪", active_run: "active-maze" }
      : url.includes("active-maze")
        ? {
            id: "active-maze",
            scenario_id: "maze",
            status: "running",
            frames: [],
          }
        : grouped(url),
  );
  render(<App />);
  await waitFor(() =>
    expect(screen.getByRole("button", { name: /交错通道/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    ),
  );
  expect(screen.getByRole("button", { name: "简单场景 1" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "全部 3" })).toBeDisabled();
});
it("treats legacy scene metadata as simple navigation", async () => {
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "简单场景 2" }));
  expect(screen.getByRole("button", { name: /找球/ })).toBeEnabled();
  expect(screen.getAllByText("目标导航")).toHaveLength(2);
});

it("uses a saved scenario name and difficulty after the catalog changes", async () => {
  const saved = {
    id: "snapshot-history",
    scenario_id: "reach",
    status: "completed",
    frames: recordedFrames,
    scenario_snapshot: {
      ...scenarios[0],
      name: "历史停靠任务",
      difficulty: "complex",
      category: "obstacle",
    },
  };
  serve((url) =>
    url === "/api/runs"
      ? [saved]
      : url.includes("snapshot-history")
        ? saved
        : grouped(url),
  );
  render(<App />);
  fireEvent.click(
    await screen.findByRole("button", {
      name: /历史停靠任务.*snapshot-history/,
    }),
  );
  expect(
    await screen.findByRole("heading", { name: "历史停靠任务" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: /snapshot-history/ }),
  ).toHaveTextContent("复杂场景");
});

it("selects 8x playback, pauses, and changes speed without jumping", async () => {
  const saved = {
    id: "speed-record",
    scenario_id: "reach",
    status: "completed",
    frames: Array.from({ length: 101 }, (_, i) => ({
      ...recordedFrames[0],
      t: i / 50,
    })),
  };
  serve((url) =>
    url === "/api/runs"
      ? [saved]
      : url.includes("speed-record")
        ? saved
        : initial(url),
  );
  render(<App />);
  expect(screen.getByRole("combobox", { name: "回放速度" })).toBeDisabled();
  fireEvent.click(await screen.findByRole("button", { name: /speed-record/ }));
  const speed = screen.getByRole("combobox", { name: "回放速度" });
  await waitFor(() => expect(speed).toBeEnabled());
  expect(speed).toHaveValue("1");
  fireEvent.change(speed, { target: { value: "8" } });
  fireEvent.click(screen.getByRole("button", { name: "播放回放" }));
  await waitFor(() =>
    expect(
      Number(
        (screen.getByRole("slider", { name: "回放时间轴" }) as HTMLInputElement)
          .value,
      ),
    ).toBeGreaterThan(20),
  );
  fireEvent.click(screen.getByRole("button", { name: "暂停回放" }));
  const stopped = (
    screen.getByRole("slider", { name: "回放时间轴" }) as HTMLInputElement
  ).value;
  fireEvent.change(speed, { target: { value: "0.5" } });
  expect(screen.getByRole("slider", { name: "回放时间轴" })).toHaveValue(
    stopped,
  );
  await new Promise((resolve) => setTimeout(resolve, 50));
  expect(screen.getByRole("slider", { name: "回放时间轴" })).toHaveValue(
    stopped,
  );
});

it("labels football and pickup tasks and offers the scenario skill", async () => {
  const skillScenes = [
    {
      ...scenarios[0],
      id: "football_left",
      name: "左脚射门",
      category: "football",
      task_type: "football",
      skill: "kick_left",
    },
    {
      ...scenarios[1],
      id: "pickup",
      name: "地面拾取试验",
      category: "pickup",
      task_type: "pickup",
      skill: "ground_pick",
    },
  ];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string) => ({
      ok: true,
      json: async () =>
        input === "/api/status"
          ? { available: true, detail: "就绪" }
          : input === "/api/scenarios"
            ? skillScenes
            : input === "/api/runs"
              ? []
              : {},
    })),
  );
  render(<App />);
  expect(await screen.findByText("足球")).toBeInTheDocument();
  expect(screen.getByText("拾取")).toBeInTheDocument();
  expect(screen.getByText(/快速试跑使用官方动作技能/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "左脚踢球" })).toBeDisabled();
});

it("sends the selected official skill while running and shows measured pickup lift", async () => {
  const scene = {
    ...scenarios[0],
    id: "pickup",
    name: "地面拾取",
    category: "pickup",
    task_type: "pickup",
    skill: "ground_pick",
  };
  const current = {
    id: "pickup-run",
    scenario_id: "pickup",
    status: "running",
    scenario_snapshot: scene,
  };
  const fetcher = vi.fn(async (input: string) => ({
    ok: true,
    json: async () =>
      input === "/api/status"
        ? { available: true, detail: "就绪", active_run: current.id }
        : input === "/api/scenarios"
          ? [scene]
          : input === "/api/runs"
            ? []
            : input.endsWith("/stop")
              ? {
                  ...current,
                  status: "completed",
                  score: {
                    success: false,
                    completion: 0,
                    duration: 5,
                    falls: 0,
                    collisions: 0,
                    details: {
                      peak_lift: 0.002,
                      picked_up: true,
                      transported: false,
                      placed: false,
                    },
                  },
                }
              : input === "/api/skill"
                ? { accepted: true }
                : current,
  }));
  vi.stubGlobal("fetch", fetcher);
  render(<App />);
  const skill = await screen.findByRole("button", { name: "地面拾取动作" });
  await waitFor(() => expect(skill).toBeEnabled());
  expect(screen.getByText(/模拟夹持/)).toBeInTheDocument();
  fireEvent.click(skill);
  await waitFor(() =>
    expect(fetcher).toHaveBeenCalledWith(
      "/api/skill",
      expect.objectContaining({
        body: JSON.stringify({ name: "ground_pick" }),
      }),
    ),
  );
  fireEvent.click(screen.getByRole("button", { name: "停止并保存" }));
  expect(await screen.findByText("实际抬升 0.2 厘米")).toBeInTheDocument();
  expect(screen.getByText("任务未完成")).toBeInTheDocument();
  expect(screen.getByText("已拾起")).toBeInTheDocument();
  expect(screen.getByText("尚未送达 B 点")).toBeInTheDocument();
  expect(screen.getByText("尚未放下")).toBeInTheDocument();
});

it("limits unsupported live skill scenes to quick trials", async () => {
  const scene = {
    ...scenarios[0],
    id: "football_left",
    name: "左脚射门",
    task_type: "football",
    skill: "kick_left",
    fast_only: true,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string) => ({
      ok: true,
      json: async () =>
        input === "/api/status"
          ? { available: true, detail: "就绪" }
          : input === "/api/scenarios"
            ? [scene]
            : [],
    })),
  );
  render(<App />);
  expect(
    await screen.findByText("此技能场景目前仅支持快速试跑。"),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "开始运行" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "快速试跑" })).toBeEnabled();
  expect(
    screen.queryByRole("button", { name: "左脚踢球" }),
  ).not.toBeInTheDocument();
});

it("replays completed A to B transport with released object and all three stages", async () => {
  const scene = {
    ...scenarios[0],
    id: "pickup_trash",
    name: "物品搬运 A → B",
    task_type: "pickup",
    target: [0.6, 0],
    objects: [{ id: "trash", kind: "trash", position: [0.1, 0, 0.01] }],
    fast_only: true,
  };
  const saved = {
    id: "transport",
    scenario_id: scene.id,
    status: "completed",
    scenario_snapshot: scene,
    objects: scene.objects,
    target: scene.target,
    frames: [
      {
        t: 0,
        position: [0, 0, 0.29],
        quaternion: [1, 0, 0, 0],
        joints: [],
        pickup: { phase: "settle", attached: false, released: true },
      },
    ],
    score: {
      success: true,
      completion: 100,
      duration: 20,
      falls: 0,
      collisions: 0,
      details: {
        picked_up: true,
        transported: true,
        placed: true,
        peak_lift: 0.09,
      },
    },
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string) => ({
      ok: true,
      json: async () =>
        input === "/api/status"
          ? { available: true, detail: "就绪" }
          : input === "/api/scenarios"
            ? [scene]
            : input === "/api/runs"
              ? [saved]
              : saved,
    })),
  );
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /transport/ }));
  expect(await screen.findByText("已送达 B 点")).toBeInTheDocument();
  expect(screen.getByText("已拾起")).toBeInTheDocument();
  expect(screen.getByText("已放下")).toBeInTheDocument();
  expect(screen.getByText("等待物品落稳 · 已松开")).toBeInTheDocument();
  expect(screen.getByText(/A 拾取点 → B 放置点/)).toBeInTheDocument();
  expect(screen.getByText("任务完成")).toBeInTheDocument();
});
