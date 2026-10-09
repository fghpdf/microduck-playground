import { I18nProvider, useI18n, type Locale } from "./i18n";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { request, type Run, type Scenario } from "./api";
import World from "./World";
import Diagnostics from "./Diagnostics";
import { playbackFrameIndex } from "./playback";
const difficulties = {
  all: "全部",
  simple: "简单场景",
  advanced: "进阶场景",
  complex: "复杂场景",
} as const;
type DifficultyFilter = keyof typeof difficulties;
const difficultyOf = (scene: Scenario) => scene.difficulty ?? "simple";
export default function App() {
  return (
    <I18nProvider>
      <AppContent />
    </I18nProvider>
  );
}
function AppContent() {
  const { t, locale, setLocale } = useI18n();
  const [status, setStatus] = useState({
    available: false,
    detail: "正在连接本地仿真…",
  });
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selected, setSelected] = useState("");
  const [difficulty, setDifficulty] = useState<DifficultyFilter>("all");
  const [runs, setRuns] = useState<Run[]>([]);
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const playbackIndex = useRef(index);
  playbackIndex.current = index;
  const controlTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const active = run?.status === "starting" || run?.status === "running";
  const fastRun = run?.mode === "fast_reference";
  const controllable = run?.status === "running" && !fastRun;
  const frames = run?.frames ?? [];
  const objectPathPoints = useMemo(() => {
    // Keep the kicker and goal readable instead of zooming out for the rolling ball.
    if (run?.task_type === "football") return [];
    const step = Math.max(1, Math.ceil(frames.length / 100));
    return frames
      .filter((_, i) => i % step === 0 || i === frames.length - 1)
      .flatMap(
        (frame) =>
          frame.objects?.map((item) => item.position) ??
          (frame.ball ? [frame.ball] : []),
      );
  }, [frames, run?.task_type]);
  const visibleScenarios = scenarios.filter(
    (s) => difficulty === "all" || difficultyOf(s) === difficulty,
  );
  const changeDifficulty = (next: DifficultyFilter) => {
    setDifficulty(next);
    const matching = scenarios.filter(
      (s) => next === "all" || difficultyOf(s) === next,
    );
    if (!matching.some((s) => s.id === selected)) {
      setSelected(matching[0]?.id ?? "");
      setRun(null);
      setPlaying(false);
      setIndex(0);
    }
  };
  const scenario =
    run?.scenario_snapshot ??
    scenarios.find((s) => s.id === (run?.scenario_id ?? selected));
  const task = {
    kind: run?.task_type ?? scenario?.task_type,
    skill: run?.skill ?? scenario?.skill,
  };
  const skillLabel =
    task?.skill === "kick_left"
      ? t("左脚踢球")
      : task?.skill === "kick_right"
        ? t("右脚踢球")
        : t("地面拾取动作");
  const fail = useCallback(
    (e: unknown) => setError(e instanceof Error ? e.message : "连接失败"),
    [],
  );
  useEffect(() => {
    let mounted = true;
    Promise.all([
      request<typeof status & { active_run?: string | null }>("/api/status"),
      request<Scenario[]>("/api/scenarios"),
      request<Run[]>("/api/runs"),
    ])
      .then(([s, c, r]) => {
        if (mounted) {
          setStatus(s);
          setScenarios(c);
          setSelected(c[0]?.id ?? "");
          setRuns(r);
          if (s.active_run)
            request<Run>(`/api/runs/${encodeURIComponent(s.active_run)}`)
              .then((current) => {
                if (mounted) {
                  setRun(current);
                  setSelected(current.scenario_id);
                  setIndex(Math.max(0, (current.frames?.length ?? 1) - 1));
                }
              })
              .catch(fail);
        }
      })
      .catch((e) => {
        if (mounted) {
          setStatus({
            available: false,
            detail: "无法连接本地服务，请启动后台后刷新页面",
          });
          fail(e);
        }
      });
    return () => {
      mounted = false;
    };
  }, [fail]);
  useEffect(() => {
    if (!active || !run) return;
    const timer = setInterval(() => {
      request<Run>(`/api/runs/${encodeURIComponent(run.id)}`)
        .then((next) => {
          if (next && typeof next === "object" && "status" in next) {
            setRun(next);
            setIndex(Math.max(0, (next.frames?.length ?? 1) - 1));
            if (next.status !== "running" && next.status !== "starting")
              request<Run[]>("/api/runs").then(setRuns).catch(fail);
          }
        })
        .catch(fail);
    }, 350);
    return () => clearInterval(timer);
  }, [active, run?.id, fail]);
  useEffect(() => {
    if (!playing || active || frames.length < 2) return;
    const startTime = frames[playbackIndex.current]?.t ?? frames[0].t;
    const startedAt = performance.now();
    let animation: number;
    const tick = () => {
      const next = playbackFrameIndex(
        frames,
        startTime,
        performance.now() - startedAt,
        playbackSpeed,
      );
      setIndex(next);
      if (next >= frames.length - 1) setPlaying(false);
      else animation = requestAnimationFrame(tick);
    };
    animation = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animation);
  }, [playing, active, frames, playbackSpeed]);
  const command = useCallback(
    (vx: number, vyaw: number) => {
      request("/api/control", { vx, vyaw }).catch(fail);
    },
    [fail],
  );
  const release = useCallback(() => {
    if (controlTimer.current) {
      clearInterval(controlTimer.current);
      controlTimer.current = null;
      command(0, 0);
    }
  }, [command]);
  const hold = useCallback(
    (vx: number, vyaw: number) => {
      if (!controllable) return;
      release();
      command(vx, vyaw);
      controlTimer.current = setInterval(() => command(vx, vyaw), 150);
    },
    [controllable, command, release],
  );
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (
        e.repeat ||
        ["INPUT", "TEXTAREA"].includes((e.target as HTMLElement).tagName)
      )
        return;
      const keys: Record<string, [number, number]> = {
        w: [0.3, 0],
        s: [0, 0],
        a: [0.3, 0.5],
        d: [0.3, -0.5],
      };
      if (keys[e.key.toLowerCase()]) {
        e.preventDefault();
        hold(...keys[e.key.toLowerCase()]);
      }
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", release);
    window.addEventListener("blur", release);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", release);
      window.removeEventListener("blur", release);
      release();
    };
  }, [hold, release]);
  const start = async (mode: "realtime" | "fast_reference" = "realtime") => {
    setBusy(true);
    setError("");
    setPlaying(false);
    try {
      const next = await request<Run>("/api/runs", {
        scenario_id: selected,
        ...(mode === "fast_reference" ? { mode } : {}),
      });
      setRun(next);
      setIndex(0);
      setRuns(await request<Run[]>("/api/runs"));
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };
  const stop = async () => {
    if (!run) return;
    release();
    try {
      setRun(
        await request<Run>(`/api/runs/${encodeURIComponent(run.id)}/stop`, {}),
      );
      setRuns(await request<Run[]>("/api/runs"));
    } catch (e) {
      fail(e);
    }
  };
  const load = async (id: string) => {
    setPlaying(false);
    try {
      const loaded = await request<Run>(`/api/runs/${encodeURIComponent(id)}`);
      setRun(loaded);
      setSelected(loaded.scenario_id);
      if (!visibleScenarios.some((s) => s.id === loaded.scenario_id))
        setDifficulty("all");
      setIndex(0);
    } catch (e) {
      fail(e);
    }
  };
  return (
    <main>
      <header>
        <a className="brand" href="/">
          ◒{" "}
          <span>
            microduck<span className="brand-light"> playground</span>
          </span>
        </a>
        <select
          className="language-select"
          aria-label="Language / 言語 / 언어"
          value={locale}
          onChange={(e) => setLocale(e.target.value as Locale)}
        >
          <option value="zh">简体中文</option>
          <option value="en">English</option>
          <option value="ja">日本語</option>
          <option value="ko">한국어</option>
        </select>
        <span className="local-tag">{t("LOCAL LAB · 本地实验室")}</span>
      </header>
      <section className="intro">
        <div className="eyebrow">A SMALL ROBOT. A WORLD OF POSSIBILITIES.</div>
        <h1>{t("让小鸭，迈出第一步。")}</h1>
        <p>{t("选一个场景，接入你的程序，看看想法如何变成动作。")}</p>
      </section>
      <div className="workspace">
        <aside>
          <div className="panel-heading">
            <h2>
              01 <span>{t("选择场景")}</span>
            </h2>
            <span>
              {scenarios.length} {t("个场景")}
            </span>
          </div>
          <div
            className="scene-filters"
            role="group"
            aria-label={t("场景难度")}
          >
            {(Object.keys(difficulties) as DifficultyFilter[]).map((key) => (
              <button
                key={key}
                disabled={active || busy}
                aria-pressed={difficulty === key}
                onClick={() => changeDifficulty(key)}
              >
                {t(difficulties[key])}{" "}
                <span>
                  {key === "all"
                    ? scenarios.length
                    : scenarios.filter((s) => difficultyOf(s) === key).length}
                </span>
              </button>
            ))}
          </div>
          <div
            className="scenarios"
            role="region"
            aria-label={
              difficulty === "all" ? t("全部场景") : t(difficulties[difficulty])
            }
            tabIndex={0}
          >
            {visibleScenarios.map((s, i) => (
              <button
                key={s.id}
                className={`scenario ${selected === s.id ? "selected" : ""}`}
                aria-pressed={selected === s.id}
                disabled={active}
                onClick={() => {
                  setSelected(s.id);
                  setRun(null);
                  setPlaying(false);
                  setIndex(0);
                }}
              >
                <span className="scenario-icon">{["↗", "◎", "⌁"][i % 3]}</span>
                <strong>{t(s.name)}</strong>
                <span>{t(s.description)}</span>
                <small className="scene-meta">
                  <span>{t(difficulties[difficultyOf(s)])}</span>
                  <span>
                    {s.category === "football"
                      ? t("足球")
                      : s.category === "pickup"
                        ? t("拾取")
                        : s.category === "terrain"
                          ? t("坡道地形")
                          : s.category === "obstacle"
                            ? t("障碍避让")
                            : t("目标导航")}
                  </span>
                  <span>{s.duration}s</span>
                </small>
              </button>
            ))}
          </div>
          <section className="control">
            <h2>
              02 <span>{t("运行与控制")}</span>
            </h2>
            <div className={`connection ${status.available ? "ready" : ""}`}>
              <i />
              {status.available ? t("官方环境已就绪") : t("等待官方仿真")}
            </div>
            <p className="detail">{t(status.detail)}</p>
            {task.kind === "pickup" && (
              <p className="hint">
                {" "}
                {t(
                  "实验性搬运：从 A 点拾起物品，带到 B 点并放下。使用接触后启动的模拟夹持，尚未校准为真实硬件抓取。",
                )}{" "}
              </p>
            )}
            <button
              className="primary"
              disabled={
                !status.available ||
                !selected ||
                active ||
                busy ||
                !!scenario?.fast_only
              }
              onClick={() => start()}
            >
              {busy ? t("正在启动…") : t("开始运行")}{" "}
              <span aria-hidden="true">↗</span>
            </button>
            {scenario?.fast_only && (
              <p className="hint">{t("此技能场景目前仅支持快速试跑。")}</p>
            )}
            <button
              className="fast-start"
              disabled={!status.available || !selected || active || busy}
              onClick={() => start("fast_reference")}
            >
              {" "}
              {t("快速试跑")}{" "}
            </button>
            <p className="hint">
              {task?.kind === "football" || task?.kind === "pickup"
                ? t(
                    "快速试跑使用官方动作技能，结果由物体的真实运动评分；接入自己的 CLI 程序请用开始运行。",
                  )
                : t(
                    "快速试跑由内置参考导航自动前往目标；接入自己的 CLI 程序请用开始运行。",
                  )}
            </p>
            <button className="stop" disabled={!active} onClick={stop}>
              {" "}
              {t("停止并保存")}{" "}
            </button>
            {task?.skill && !scenario?.fast_only && (
              <button
                className="fast-start"
                disabled={!controllable || busy}
                onClick={async () => {
                  release();
                  setBusy(true);
                  try {
                    await request("/api/skill", { name: task.skill });
                  } catch (e) {
                    fail(e);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                {skillLabel}
              </button>
            )}
            <div className="keys">
              {[
                ["W", t("前进"), 0.3, 0],
                ["A", t("左转弯"), 0.3, 0.5],
                ["S", t("停车"), 0, 0],
                ["D", t("右转弯"), 0.3, -0.5],
              ].map(([key, label, vx, yaw]) => (
                <button
                  key={key}
                  data-key={key}
                  disabled={!controllable}
                  aria-label={String(label)}
                  onPointerDown={(e) => {
                    e.currentTarget.setPointerCapture(e.pointerId);
                    hold(Number(vx), Number(yaw));
                  }}
                  onPointerUp={release}
                  onPointerCancel={release}
                >
                  <kbd>{key}</kbd>
                  <small>{label}</small>
                </button>
              ))}
            </div>
            <p className="hint">{t("转弯时会向前行走，S 停车 · 松开即停止")}</p>
          </section>
        </aside>
        <section className="stage">
          <div className="stage-top">
            <div>
              <span className="eyebrow">SIMULATION / PLAYBACK</span>
              <h2>
                {scenario?.name ? t(scenario.name) : t("Microduck 仿真空间")}
              </h2>
            </div>
            <span className="chip">
              {active && fastRun
                ? t("● 快速计算")
                : run?.status === "starting"
                  ? t("◌ 正在站稳")
                  : active
                    ? t("● 实时运行")
                    : frames.length
                      ? t("◷ 记录回放")
                      : t("○ 尚未运行")}
            </span>
          </div>
          <World
            objectPathPoints={objectPathPoints}
            pickupStart={
              task.kind === "pickup"
                ? (run?.objects ?? scenario?.objects)?.find(
                    (item) => item.kind === "trash",
                  )?.position
                : undefined
            }
            objects={run ? (run.objects ?? []) : (scenario?.objects ?? [])}
            goal={run?.goal ?? scenario?.goal}
            terrain={run ? (run.terrain ?? []) : (scenario?.terrain ?? [])}
            frame={frames[index]}
            target={run?.target ?? scenario?.target}
            obstacles={
              run ? (run.obstacles ?? []) : (scenario?.obstacles ?? [])
            }
          />
          <div className="world-label">
            {" "}
            {t("简化外观 · 官方物理")}{" "}
            {task.kind === "pickup" ? t(" · A 拾取点 → B 放置点") : ""}
          </div>
          {task.kind === "pickup" && frames[index]?.pickup && (
            <p className="task-phase">
              {(
                {
                  approach: t("靠近 A 点"),
                  pick: t("拾取物品"),
                  lift: t("抬起物品"),
                  transport: t("搬运至 B 点"),
                  place: t("放下物品"),
                  settle: t("等待物品落稳"),
                } as Record<string, string>
              )[frames[index].pickup?.phase ?? ""] ?? t("搬运记录")}{" "}
              ·{" "}
              {frames[index].pickup?.attached
                ? t("正在夹持")
                : frames[index].pickup?.released
                  ? t("已松开")
                  : t("尚未夹持")}
            </p>
          )}
          {!frames.length && (
            <div className="waiting">
              {active && fastRun
                ? t("正在快速计算完整运行记录…")
                : run?.status === "starting"
                  ? t("正在启动并等待机器人站稳…")
                  : status.available
                    ? t("准备好后，开始第一次实验")
                    : t("连接官方仿真后即可开始")}
              <small>{t("此画面为场景预览，未生成仿真结果")}</small>
            </div>
          )}
          <div className="timeline">
            <button
              type="button"
              className="timeline-step"
              aria-label={t("上一帧")}
              title={t("上一帧")}
              disabled={active || frames.length < 2 || index <= 0}
              onClick={() => {
                setPlaying(false);
                setIndex((i) => Math.max(0, i - 1));
              }}
            >
              ⎸◀
            </button>
            <button
              aria-label={playing ? t("暂停回放") : t("播放回放")}
              disabled={active || frames.length < 2}
              onClick={() => {
                if (!playing && index >= frames.length - 1) setIndex(0);
                setPlaying((p) => !p);
              }}
            >
              {playing ? "Ⅱ" : "▶"}
            </button>
            <button
              type="button"
              className="timeline-step"
              aria-label={t("下一帧")}
              title={t("下一帧")}
              disabled={
                active || frames.length < 2 || index >= frames.length - 1
              }
              onClick={() => {
                setPlaying(false);
                setIndex((i) => Math.min(frames.length - 1, i + 1));
              }}
            >
              ▶⎹
            </button>
            <input
              aria-label={t("回放时间轴")}
              type="range"
              min="0"
              max={Math.max(0, frames.length - 1)}
              value={index}
              disabled={active || !frames.length}
              onChange={(e) => {
                setPlaying(false);
                setIndex(Number(e.target.value));
              }}
            />
            <span>
              {(frames[index]?.t ?? 0).toFixed(1)} /{" "}
              {(frames.at(-1)?.t ?? 0).toFixed(1)}s
            </span>
            <label className="playback-speed">
              {" "}
              {t("回放速度")}{" "}
              <select
                aria-label={t("回放速度")}
                value={playbackSpeed}
                disabled={active || frames.length < 2}
                onChange={(e) => setPlaybackSpeed(Number(e.target.value))}
              >
                {[0.5, 1, 2, 4, 8].map((speed) => (
                  <option key={speed} value={speed}>
                    {speed}×{speed === 1 ? t(" 正常速度") : ""}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="score">
            {run?.score ? (
              <>
                <strong
                  className={`score-badge ${run.score.success ? "success" : "fail"}`}
                >
                  {run.score.success ? t("任务完成") : t("任务未完成")}
                </strong>
                <span className="score-metric">
                  {" "}
                  {t("完成度")} {Math.round(run.score.completion)}%
                </span>
                <span className="score-metric">
                  {fastRun ? t("仿真时长") : t("耗时")}{" "}
                  {run.score.duration.toFixed(1)}s
                </span>
                {run.wall_duration !== undefined && (
                  <span className="score-metric">
                    {" "}
                    {t("计算耗时")} {run.wall_duration.toFixed(1)}s
                  </span>
                )}
                {task.kind === "football" && run.score.details && (
                  <span className="score-pill">
                    {run.score.details.goal_crossed
                      ? t("足球进入球门")
                      : t("足球未进入球门")}
                  </span>
                )}
                {task.kind === "pickup" && run.score.details && (
                  <span className="score-metric">
                    {" "}
                    {t("实际抬升")}{" "}
                    {typeof run.score.details.peak_lift === "number"
                      ? (run.score.details.peak_lift * 100).toFixed(1)
                      : "0.0"}{" "}
                    {t("厘米")}{" "}
                  </span>
                )}
                {task.kind === "pickup" &&
                  run.score.details &&
                  typeof run.score.details.picked_up === "boolean" && (
                    <>
                      <span className="score-pill">
                        {run.score.details.picked_up
                          ? t("已拾起")
                          : t("尚未拾起")}
                      </span>
                      <span className="score-pill">
                        {run.score.details.transported
                          ? t("已送达 B 点")
                          : t("尚未送达 B 点")}
                      </span>
                      <span className="score-pill">
                        {run.score.details.placed ? t("已放下") : t("尚未放下")}
                      </span>
                    </>
                  )}
                <span
                  className={`score-metric ${run.score.falls > 0 ? "warning" : ""}`}
                >
                  {" "}
                  {t("跌倒")} {run.score.falls}
                </span>
                <span
                  className={`score-metric ${run.score.collisions > 0 ? "warning" : ""}`}
                >
                  {" "}
                  {t("碰撞")} {run.score.collisions}
                </span>
              </>
            ) : (
              <>
                <strong>{t("等待第一次运行")}</strong>
                <span>{t("完成后显示评分与运行记录")}</span>
              </>
            )}
          </div>
        </section>
      </div>
      {run && <Diagnostics data={run.diagnostics} />}
      {(error || run?.error) && (
        <div role="alert" className="error">
          {t(error || run?.error || "")}
        </div>
      )}
      <section className="history">
        <div className="panel-heading">
          <h2>
            03 <span>{t("运行记录")}</span>
          </h2>
          <span>{t("每次尝试，都是一次进步")}</span>
        </div>
        {runs.length ? (
          <div className="history-list">
            {runs.map((r) => (
              <button disabled={active} key={r.id} onClick={() => load(r.id)}>
                <strong>
                  {t(
                    r.scenario_snapshot?.name ??
                      scenarios.find((s) => s.id === r.scenario_id)?.name ??
                      r.scenario_id,
                  )}
                </strong>
                <span>{r.id}</span>
                <small>
                  {t(
                    difficulties[
                      r.scenario_snapshot?.difficulty ??
                        r.difficulty ??
                        scenarios.find((s) => s.id === r.scenario_id)
                          ?.difficulty ??
                        "simple"
                    ],
                  )}{" "}
                  · {t(r.status)}
                </small>
                <b>↗</b>
              </button>
            ))}
          </div>
        ) : (
          <p>{t("还没有记录。启动官方仿真，完成你的第一次实验。")}</p>
        )}
      </section>
      <footer>
        MICRODUCK PLAYGROUND{" "}
        <span>{t("本地执行 · 真实记录 · 可复现回放")}</span>
      </footer>
    </main>
  );
}
