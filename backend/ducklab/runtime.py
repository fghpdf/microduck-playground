import asyncio
from copy import deepcopy
import json
import math
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

from .protocol import rpc
from .diagnostics import Diagnostics
from .scoring import score_run
from .skill_scoring import score_scene
from .fast_runtime import FastRuntimeMixin

ROOT = Path(__file__).resolve().parents[3]
PROJECT = ROOT / "microduck-local"
OFFICIAL = ROOT / "vendor" / "microduck"
RL = ROOT / "vendor" / "microduck_rl"


class OfficialRuntime(FastRuntimeMixin):
    def __init__(self, data_dir=PROJECT / "data"):
        self.data_dir = Path(data_dir)
        self.training_tuning = os.environ.get("DUCKLAB_TRAINING_TUNING") == "1"
        self.active = None
        self.task = None
        self.stop_event = None
        self.diagnostics = None
        self.processes = ()
        self.state_dir = None
        self.log = None
        self.runs = {}
        self.policy_dir = self.data_dir / "policies" / "current"
        self.port = int(os.environ.get("DUCKLAB_BODY_PORT", "17801"))
        for path in sorted((self.data_dir / "runs").glob("*.json")):
            try:
                run = json.loads(path.read_text())
                run = {**run, "created_at": run.get("created_at", path.stat().st_mtime)}
                self.runs = {**self.runs, run["id"]: run}
            except (OSError, ValueError, KeyError):
                print(f"Cannot read saved run: {path}", file=sys.stderr)

    def status(self):
        missing = [name for name, path in (
            ("robotd", OFFICIAL / "target/debug/robotd"),
            ("robotctl", OFFICIAL / "target/debug/robotctl"),
            ("官方行走策略", self.policy_dir / "alpha_walking.onnx"),
            ("官方站立策略", self.policy_dir / "alpha_stand.onnx"),
            ("机器人模型", RL / "src/mjlab_microduck/sim/body_server.py"),
        ) if not path.exists()]
        return {"available": not missing, "backend": "official",
                "detail": "缺少：" + "、".join(missing) if missing else "官方 MuJoCo 与控制服务已准备好",
                "version": "microduck 0.15.1", "active_run": self.active,
                "socket": str(self.socket) if self.state_dir and self.active and
                self.runs[self.active].get("mode") != "fast_reference" else None}

    @property
    def socket(self):
        if self.state_dir is None:
            raise RuntimeError("当前没有运行中的仿真")
        return self.state_dir / "robot.sock"

    def list_runs(self):
        return [{key: val for key, val in run.items() if key != "frames"}
                for run in sorted(self.runs.values(), key=lambda item: item.get("created_at", 0), reverse=True)]

    def get_run(self, run_id):
        return self.runs.get(run_id)

    def save(self, run):
        self.runs = {**self.runs, run["id"]: run}
        directory = self.data_dir / "runs"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{run['id']}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(run, ensure_ascii=False, allow_nan=False))
        temporary.replace(path)

    async def start(self, scenario, mode="realtime"):
        if mode not in ("realtime", "fast_reference"):
            raise ValueError("未知运行模式")
        if scenario.get("fast_only") and mode != "fast_reference":
            raise ValueError("此技能场景目前仅支持快速试跑")
        if self.active:
            raise ValueError("已有仿真正在运行，请先停止")
        if not self.status()["available"]:
            raise RuntimeError(self.status()["detail"])
        scenario = deepcopy(scenario)
        self.scenario = scenario
        run_id = uuid.uuid4().hex
        self.state_dir = Path(tempfile.mkdtemp(prefix="ducklab-", dir="/private/tmp" if sys.platform == "darwin" else "/tmp"))
        run = {"id": run_id, "created_at": time.time(), "scenario_id": scenario["id"], "status": "starting", "frames": [],
               "difficulty": scenario.get("difficulty", "simple"),
               "category": scenario.get("category", "navigation"), "scenario_snapshot": deepcopy(scenario),
               "task_type": scenario.get("task_type", "navigation"), "skill": scenario.get("skill"),
               "objects": deepcopy(scenario.get("objects", [])), "goal": deepcopy(scenario.get("goal")),
               "mode": mode, "events": [], "score": None, "target": scenario["target"], "source": "official-mujoco",
               "obstacles": deepcopy(scenario.get("obstacles", [])), "terrain": deepcopy(scenario.get("terrain", [])),
               "versions": {**self.provenance(), "target_frame": scenario.get("target_frame", "standing-body-relative"),
                            "scene": "terrain-v1" if scenario.get("terrain") else "obstacles-v1" if scenario.get("obstacles") else "official-floor-v1"}, "diagnostics": {"commands": [], "health": []}}
        self.runs = {**self.runs, run_id: run}
        self.active = run_id
        self.stop_event = asyncio.Event()
        if mode == "fast_reference":
            run = {**run, "source": "official-mujoco-offline", "versions": {
                **run["versions"], "profile": "offline-alpha-bam-v1",
                "controller": "reference-navigation", "initial_condition": "official-STAND2"}}
            self.runs = {**self.runs, run_id: run}
            self.diagnostics = None
            self.task = asyncio.create_task(self.execute_fast(run_id, scenario))
            return run
        self.diagnostics = Diagnostics(self.socket, rpc, sim_time=lambda: (
            self.runs[run_id]["frames"][-1]["t"] if self.runs[run_id]["frames"] else None))
        self.task = asyncio.create_task(self.execute(run_id, scenario))
        return run

    def provenance(self):
        def revision(repo):
            head = repo / ".git/HEAD"
            if not head.exists():
                return "unknown"
            value = head.read_text().strip()
            if not value.startswith("ref: "):
                return value
            ref = value.removeprefix("ref: ")
            path = repo / ".git" / ref
            if path.exists():
                return path.read_text().strip()
            packed = repo / ".git/packed-refs"
            if packed.exists():
                return next((line.split()[0] for line in packed.read_text().splitlines()
                             if line.endswith(" " + ref)), "unknown")
            return "unknown"
        return {"microduck": revision(OFFICIAL), "microduck_rl": revision(RL), "policy_set": "v5",
                "target_frame": "standing-body-relative", "physics_dt": 0.005, "control_hz": 50, "scene": "official-floor-v1", "scoring": "arrival-v1",
                "walk": "alpha_walking.onnx", "stand": "alpha_stand.onnx", "actuator": "bam_m6",
                "profile": "alpha-bam-training-v1" if self.training_tuning else "alpha-walk-bam-v1"}

    async def execute(self, run_id, scenario):
        run = self.runs[run_id]
        try:
            await self.launch()
            self.diagnostics.start()
            body = self.processes[0]
            # Give the official standing policy time to rise before scoring starts.
            warmup_until = asyncio.get_running_loop().time() + 4.0
            origin = None
            wall_start = None
            upright_since = None
            reached_limit = False
            while not self.stop_event.is_set():
                line = await asyncio.wait_for(body.stdout.readline(), 3.0)
                if not line:
                    raise RuntimeError("仿真进程提前退出，本次运行未完成")
                if not line.startswith(b'{'):
                    continue
                frame = json.loads(line)
                if frame.get("type") != "frame":
                    continue
                now = asyncio.get_running_loop().time()
                if now < warmup_until:
                    continue
                if origin is None:
                    if frame["fallen"] or frame["position"][2] < 0.095:
                        upright_since = None
                    elif upright_since is None:
                        upright_since = now
                    if now > warmup_until + 10 and (upright_since is None or now - upright_since < 0.5):
                        raise RuntimeError("机器人未能站稳，本次场景未开始，请查看日志并重试")
                    if upright_since is None or now - upright_since < 0.5:
                        continue
                    origin, wall_start = frame["t"], now
                    w, x, y, z = frame["quaternion"]
                    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
                    forward, left = scenario["target"]
                    target = [frame["position"][0] + forward * math.cos(yaw) - left * math.sin(yaw),
                              frame["position"][1] + forward * math.sin(yaw) + left * math.cos(yaw)]
                    if scenario.get("target_frame") == "world":
                        target = list(scenario["target"])
                    run = {**run, "status": "running", "target": target,
                           "start_pose": {"position": list(frame["position"]),
                                          "quaternion": list(frame["quaternion"])}}
                frame = {**frame, "t": round(frame["t"] - origin, 6), "wall_t": round(now - wall_start, 6)}
                run = {**run, "frames": [*run["frames"], frame]}
                run = {**run, "diagnostics": self.diagnostics.snapshot()}
                self.runs = {**self.runs, run_id: run}
                if frame["t"] >= scenario["duration"]:
                    reached_limit = True
                    break
                if self.processes[1].returncode is not None:
                    raise RuntimeError("官方控制服务已退出，请查看本地运行日志")
            if origin is None and not self.stop_event.is_set():
                raise RuntimeError("没有收到 MuJoCo 世界状态")
            run = {**run, "status": "completed" if reached_limit else "stopped",
                   "score": score_run(run["frames"], run["target"])}
        except asyncio.CancelledError:
            run = self.runs[run_id]
            run = {**run, "status": "stopped", "score": score_run(run["frames"], run["target"])}
        except Exception as error:
            run = {**self.runs[run_id], "status": "failed", "error": str(error), "score": None}
        finally:
            try:
                self.runs = {**self.runs, run_id: {**run, "diagnostics": self.diagnostics.snapshot()}}
                await self.diagnostics.close()
                run = {**run, "diagnostics": self.diagnostics.snapshot()}
                await self.cleanup()
                self.save(run)
            except OSError as error:
                self.runs = {**self.runs, run_id: {**run, "status": "failed", "error": f"记录保存失败：{error}"}}
            finally:
                self.active = None

    def policy_config(self):
        policies = {"walk": "alpha_walking", "stand": "alpha_stand", "sitstand": "alpha_sitstand",
                    "ground_pick": "alpha_ground_pick", "kick_left": "ball_kick_left",
                    "kick_right": "ball_kick_right", "roulade": "roulade"}
        tuning = "action_scale = 1.0\nhead_lowpass = 1.0\nlegs_lowpass = 1.0\n" if self.training_tuning else ""
        return "[policy]\nenabled = true\n" + tuning + "".join(
            f'{key} = "{self.policy_dir / (name + ".onnx")}"\n' for key, name in policies.items())

    async def launch(self):
        library = next(iter(Path(sys.prefix).glob("lib/python*/site-packages/onnxruntime/capi/libonnxruntime*.dylib")), None)
        if library is None:
            library = next(iter(Path(sys.prefix).glob("lib/python*/site-packages/onnxruntime/capi/libonnxruntime.so*")), None)
        if library is None:
            raise RuntimeError("缺少 ONNX Runtime 动态库")
        directory = self.data_dir / "logs"
        directory.mkdir(parents=True, exist_ok=True)
        self.log = (directory / f"{self.active}.log").open("wb")
        params = self.state_dir / "robotd.toml"
        params.write_text(self.policy_config())
        body = await asyncio.create_subprocess_exec(sys.executable, "-m", "ducklab.body_runner",
            "--rl", str(RL), "--port", str(self.port),
            *(["--scenario", self.scenario["id"]] if getattr(self, "scenario", {}).get("obstacles") or getattr(self, "scenario", {}).get("terrain") else []), stdout=asyncio.subprocess.PIPE, stderr=self.log)
        self.processes = (body,)
        # Wait for the observer's first frame: the official body server is now
        # listening. A fixed sleep let robotd boot before the body was ready.
        async with asyncio.timeout(10):
            while True:
                line = await body.stdout.readline()
                if not line:
                    raise RuntimeError("MuJoCo 身体启动失败")
                if line.startswith(b'{') and json.loads(line).get("type") == "frame":
                    break
        robot = await asyncio.create_subprocess_exec(str(OFFICIAL / "target/debug/robotd"),
            "--sim", f"127.0.0.1:{self.port}", "--socket", str(self.socket), "--params", str(params),
            env={**os.environ, "ORT_DYLIB_PATH": str(library)}, stdout=self.log, stderr=self.log)
        self.processes = (body, robot)
        for _ in range(100):
            if robot.returncode is not None or body.returncode is not None:
                raise RuntimeError("官方仿真启动失败，请查看 data/logs 中本次日志")
            if self.socket.exists():
                result = await rpc(self.socket, "robot.enable", {"on": True})
                if not result or not result.get("accepted"):
                    raise RuntimeError("官方运动策略未能启用")
                return
            await asyncio.sleep(0.05)
        raise RuntimeError("等待官方控制服务超时")

    async def control(self, vx, vyaw):
        if not self.active or self.runs[self.active]["status"] != "running":
            raise ValueError("请先开始场景，等待机器人站稳")
        run_id = self.active
        if self.runs[run_id].get("mode") == "fast_reference":
            raise ValueError("快速试跑由内置导航程序控制，请使用实时模式接入自己的程序")
        diagnostics = self.diagnostics
        try:
            return await diagnostics.command(vx, vyaw)
        finally:
            run = self.runs[run_id]
            self.runs = {**self.runs, run_id: {**run, "diagnostics": diagnostics.snapshot()}}

    async def skill(self, name):
        if name not in ("kick_left", "kick_right", "ground_pick"):
            raise ValueError("未知动作")
        if not self.active or self.runs[self.active]["status"] != "running":
            raise ValueError("请先开始实时场景并等待站稳")
        if self.runs[self.active].get("mode") == "fast_reference":
            raise ValueError("快速试跑自动执行动作")
        result = await rpc(self.socket, "robot.do", {"skill": name})
        if not result or not result.get("accepted"):
            raise ValueError("官方控制服务暂时不能执行这个动作")
        return result

    async def stop(self, run_id):
        if run_id != self.active:
            if run_id in self.runs:
                return self.runs[run_id]
            raise ValueError("找不到该运行记录")
        self.stop_event.set()
        if self.runs[run_id].get("mode") == "fast_reference":
            await asyncio.sleep(0)  # Enter lifecycle before cancellation so cleanup always runs.
            if not self.task.done():
                self.task.cancel()
        await asyncio.shield(self.task)
        return self.runs[run_id]

    async def cleanup(self):
        for process in reversed(self.processes):
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), 3.0)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
        self.processes = ()
        if self.log:
            self.log.close()
            self.log = None
        if self.state_dir:
            import shutil
            shutil.rmtree(self.state_dir, ignore_errors=True)
            self.state_dir = None

    async def close(self):
        if self.active and self.task:
            await self.stop(self.active)
