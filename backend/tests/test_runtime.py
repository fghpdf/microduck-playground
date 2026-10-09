"""Lifecycle tests exercise the official bridge without launching native binaries."""
import asyncio
import math
import io
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ducklab import runtime as module
from ducklab.runtime import OfficialRuntime

SCENARIO = {"id": "arrival", "target": [1, 0], "duration": 1}


def world_frame(t, x=0):
    return {"type": "frame", "t": t, "position": [x, 0, .2],
            "quaternion": [1, 0, 0, 0], "joints": [], "fallen": False,
            "collisions": 0}


@pytest.fixture
def runtime(tmp_path):
    return OfficialRuntime(tmp_path)


def ready(monkeypatch, runtime):
    monkeypatch.setattr(runtime, "status", lambda: {"available": True})


def test_missing_dependencies_prevent_run(runtime, monkeypatch, tmp_path):
    monkeypatch.setattr(module, "OFFICIAL", tmp_path / "missing-official")
    monkeypatch.setattr(module, "RL", tmp_path / "missing-rl")
    assert not runtime.status()["available"]
    with pytest.raises(RuntimeError, match="缺少"):
        asyncio.run(runtime.start(SCENARIO))
    assert runtime.active is None and runtime.list_runs() == []
    with pytest.raises(RuntimeError, match="没有运行"):
        _ = runtime.socket


def test_saved_runs_survive_restart_and_bad_files_are_skipped(runtime, tmp_path):
    run = {"id": "saved", "created_at": 123, "status": "completed", "frames": [world_frame(0)]}
    runtime.save(run)
    directory = tmp_path / "runs"
    (directory / "corrupt.json").write_text("invalid")
    (directory / "missing-id.json").write_text("{}")
    restored = OfficialRuntime(tmp_path)
    assert restored.get_run("saved") == run
    assert restored.get_run("absent") is None
    assert restored.list_runs() == [{"id": "saved", "created_at": 123, "status": "completed"}]
    assert not list(directory.glob("*.tmp"))


def test_provenance_records_checked_out_sources(runtime, monkeypatch, tmp_path):
    for name in ("official", "rl"):
        refs = tmp_path / name / ".git/refs/heads"
        refs.mkdir(parents=True)
        (refs / "main").write_text(name + "-revision\n")
        (refs / "old").write_text("incorrect-revision\n")
        (refs.parents[1] / "HEAD").write_text("ref: refs/heads/main\n")
    monkeypatch.setattr(module, "OFFICIAL", tmp_path / "official")
    monkeypatch.setattr(module, "RL", tmp_path / "rl")
    versions = runtime.provenance()
    assert versions["microduck"] == "official-revision"
    assert versions["microduck_rl"] == "rl-revision"
    assert versions["walk"] == "alpha_walking.onnx"
    assert versions["stand"] == "alpha_stand.onnx"
    assert versions["profile"] == "alpha-walk-bam-v1"
    assert versions["physics_dt"] * versions["control_hz"] < 1


def test_run_exclusivity_controls_and_stop_persist_partial_result(runtime, monkeypatch):
    ready(monkeypatch, runtime)
    rpc = AsyncMock(return_value={"accepted": True})
    monkeypatch.setattr(module, "rpc", rpc)

    async def launch():
        await asyncio.Event().wait()

    monkeypatch.setattr(runtime, "launch", launch)

    async def exercise():
        run = await runtime.start(SCENARIO)
        await asyncio.sleep(0)  # Enter the lifecycle before cancelling.
        with pytest.raises(ValueError, match="已有"):
            await runtime.start(SCENARIO)
        with pytest.raises(ValueError, match="站稳"):
            await runtime.control(.1, .2)
        runtime.runs = {**runtime.runs, run["id"]: {**run, "status": "running",
                         "frames": [world_frame(0), world_frame(.5, 1)]}}
        assert await runtime.control(.1, .2) == {"accepted": True}
        rpc.assert_awaited_once_with(runtime.socket, "robot.move", {"vx": .1, "vy": 0.0, "vyaw": .2})
        runtime.task.cancel()
        await runtime.task
        stopped = await runtime.stop(run["id"])
        assert stopped["status"] == "stopped" and stopped["score"]["completion"] == 100
        assert runtime.active is None and runtime.state_dir is None
        assert OfficialRuntime(runtime.data_dir).get_run(run["id"]) == stopped
        assert await runtime.stop(run["id"]) == stopped
        with pytest.raises(ValueError, match="找不到"):
            await runtime.stop("unknown")
        with pytest.raises(ValueError):
            await runtime.control(0, 0)
        await runtime.close()

    asyncio.run(exercise())


def test_launch_failure_is_recorded_and_resources_removed(runtime, monkeypatch):
    ready(monkeypatch, runtime)
    monkeypatch.setattr(runtime, "launch", AsyncMock(side_effect=RuntimeError("native process failed")))

    async def exercise():
        run = await runtime.start(SCENARIO)
        state_dir = runtime.state_dir
        await runtime.task
        failed = runtime.get_run(run["id"])
        assert failed["status"] == "failed" and failed["error"] == "native process failed"
        assert failed["score"] is None
        assert not state_dir.exists() and runtime.active is None
        assert OfficialRuntime(runtime.data_dir).get_run(run["id"]) == failed

    asyncio.run(exercise())


@pytest.mark.parametrize("lines,robot_exit,expected", [
    ([b"diagnostic\n", b'{"type":"ready"}\n', world_frame(99.5), world_frame(100), world_frame(100.5, 1), world_frame(101, 1)], None, "completed"),
    ([], None, "failed"),
    ([world_frame(99.5), world_frame(100)], 1, "failed"),
    ([b"{invalid\n"], None, "failed"),
])
def test_world_stream_completion_and_failures(runtime, monkeypatch, lines, robot_exit, expected):
    ready(monkeypatch, runtime)
    clock = iter([0, 5, 5.5, 6, 6.5, 7])
    # Replace only this module's asyncio facade; the real loop continues normally.
    facade = SimpleNamespace(**{name: getattr(asyncio, name) for name in
        ("create_task", "wait_for", "CancelledError", "TimeoutError", "Event")},
        get_running_loop=lambda: SimpleNamespace(time=lambda: next(clock)))
    monkeypatch.setattr(module, "asyncio", facade)
    stream = AsyncMock()
    stream.readline.side_effect = [json.dumps(line).encode() + b"\n" if isinstance(line, dict) else line
                                  for line in lines] + [b""]
    body = SimpleNamespace(stdout=stream, returncode=0)
    robot = SimpleNamespace(returncode=robot_exit)

    async def launch():
        runtime.processes = (body, robot)
    monkeypatch.setattr(runtime, "launch", launch)
    monkeypatch.setattr(runtime, "cleanup", AsyncMock())

    async def exercise():
        run = await runtime.start(SCENARIO)
        await runtime.task
        result = runtime.get_run(run["id"])
        assert result["status"] == expected
        assert runtime.active is None
        if expected == "completed":
            assert [f["t"] for f in result["frames"]] == [0, .5, 1]
            assert result["score"]["success"]
        else:
            assert result["error"] and result["score"] is None
        runtime.cleanup.assert_awaited_once()
    asyncio.run(exercise())


def test_cleanup_terminates_then_kills_unresponsive_process(runtime, tmp_path):
    process = SimpleNamespace(returncode=None, terminate=lambda: None, kill=lambda: None,
                              wait=AsyncMock(side_effect=[asyncio.TimeoutError(), 0]))
    from unittest.mock import Mock
    process.terminate = Mock()
    process.kill = Mock()
    runtime.processes = (process,)
    runtime.log = io.BytesIO()
    log = runtime.log
    runtime.state_dir = tmp_path / "state"
    runtime.state_dir.mkdir()
    asyncio.run(runtime.cleanup())
    process.terminate.assert_called_once()
    process.kill.assert_called_once()
    assert process.wait.await_count == 2
    assert log.closed and runtime.log is None
    assert runtime.processes == () and runtime.state_dir is None


@pytest.mark.parametrize("mode", ["ready", "rejected", "exited", "timeout", "body-eof", "missing-library"])
def test_native_launch_enables_policy_or_reports_startup_problem(runtime, monkeypatch, tmp_path, mode):
    runtime.active = "launch"
    runtime.state_dir = tmp_path / "state"
    runtime.state_dir.mkdir()
    library = tmp_path / "lib/python3/site-packages/onnxruntime/capi/libonnxruntime.so"
    if mode != "missing-library":
        library.parent.mkdir(parents=True)
        library.touch()
    monkeypatch.setattr(module.sys, "prefix", str(tmp_path))
    if mode in ("ready", "rejected"):
        runtime.socket.touch()
    stream = AsyncMock()
    stream.readline.side_effect = ([b"diagnostic\n", b'{"type":"ready"}\n', b""]
                                  if mode == "body-eof" else
                                  [b"diagnostic\n", b'{"type":"ready"}\n',
                                   json.dumps(world_frame(0)).encode() + b"\n"])
    body = SimpleNamespace(returncode=None, stdout=stream)
    robot = SimpleNamespace(returncode=1 if mode == "exited" else None)
    spawn = AsyncMock(side_effect=[body, robot])
    facade = SimpleNamespace(create_subprocess_exec=spawn, sleep=AsyncMock(),
                             subprocess=asyncio.subprocess, timeout=asyncio.timeout)
    monkeypatch.setattr(module, "asyncio", facade)
    rpc = AsyncMock(return_value={"accepted": mode == "ready"})
    monkeypatch.setattr(module, "rpc", rpc)
    if mode == "ready":
        asyncio.run(runtime.launch())
        rpc.assert_awaited_once_with(runtime.socket, "robot.enable", {"on": True})
        assert runtime.processes == (body, robot)
        robot_args = spawn.await_args_list[1]
        assert "--sim" in robot_args.args and "--socket" in robot_args.args
        assert robot_args.kwargs["env"]["ORT_DYLIB_PATH"] == str(library)
        import tomllib
        params = tomllib.loads((runtime.state_dir / "robotd.toml").read_text())
        assert params["policy"]["walk"] == str(runtime.policy_dir / "alpha_walking.onnx")
        assert params["policy"]["stand"] == str(runtime.policy_dir / "alpha_stand.onnx")
    else:
        with pytest.raises(RuntimeError):
            asyncio.run(runtime.launch())
        if mode == "missing-library":
            spawn.assert_not_awaited()
        if mode == "body-eof":
            assert spawn.await_count == 1  # Never boot control before physics is ready.
    if runtime.log:
        runtime.log.close()


def test_close_stops_current_run(runtime, monkeypatch):
    runtime.active = "current"
    runtime.task = object()
    stop = AsyncMock()
    monkeypatch.setattr(runtime, "stop", stop)
    asyncio.run(runtime.close())
    stop.assert_awaited_once_with("current")


def test_stop_immediately_after_start_cleans_up_and_can_start_again(runtime, monkeypatch):
    ready(monkeypatch, runtime)
    async def launch():
        runtime.processes = (SimpleNamespace(stdout=None),)
    monkeypatch.setattr(runtime, "launch", launch)
    monkeypatch.setattr(runtime, "cleanup", AsyncMock())

    async def exercise():
        run = await runtime.start(SCENARIO)
        result = await runtime.stop(run["id"])
        assert result["status"] == "stopped" and result["frames"] == []
        assert runtime.active is None
        another = await runtime.start(SCENARIO)
        assert another["id"] != run["id"]
        await runtime.stop(another["id"])
    asyncio.run(exercise())


def test_save_failure_releases_session_and_reports_loss_of_record(runtime, monkeypatch):
    ready(monkeypatch, runtime)
    monkeypatch.setattr(runtime, "launch", AsyncMock(side_effect=RuntimeError("startup failed")))
    from unittest.mock import Mock
    monkeypatch.setattr(runtime, "save", Mock(side_effect=OSError("disk full")))

    async def exercise():
        run = await runtime.start(SCENARIO)
        await runtime.task
        assert runtime.active is None and runtime.state_dir is None
        assert runtime.get_run(run["id"])["status"] == "failed"
        assert "disk full" in runtime.get_run(run["id"])["error"]
    asyncio.run(exercise())


@pytest.mark.parametrize("head,packed,expected", [
    ("detached-commit", None, "detached-commit"),
    ("ref: refs/heads/release", "# pack-refs\nwrong refs/heads/main\ncorrect refs/heads/release\n", "correct"),
    ("ref: refs/heads/missing", "other refs/heads/main\n", "unknown"),
    ("ref: refs/heads/missing", None, "unknown"),
])
def test_provenance_detached_and_packed_refs(runtime, monkeypatch, tmp_path, head, packed, expected):
    repo = tmp_path / "official"
    (repo / ".git").mkdir(parents=True)
    (repo / ".git/HEAD").write_text(head)
    if packed:
        (repo / ".git/packed-refs").write_text(packed)
    monkeypatch.setattr(module, "OFFICIAL", repo)
    monkeypatch.setattr(module, "RL", tmp_path / "absent")
    assert runtime.provenance()["microduck"] == expected
    assert runtime.provenance()["microduck_rl"] == "unknown"


@pytest.mark.parametrize("recovers", [True, False])
def test_standing_gate_resets_on_fall_and_times_out_without_scoring(runtime, monkeypatch, recovers):
    ready(monkeypatch, runtime)
    upright = world_frame(1)
    fallen = {**world_frame(2), "fallen": True}
    low = {**world_frame(3), "position": [0, 0, .05]}
    if recovers:
        frames = [upright, fallen, low, world_frame(4), world_frame(5), world_frame(6, 1), world_frame(6.5, 1)]
        times = [0, 5, 5.2, 5.3, 6, 6.6, 7.6, 8.1]
    else:
        frames = [upright, fallen, low]
        times = [0, 5, 6, 15]
    clock = iter(times)
    facade = SimpleNamespace(**{name: getattr(asyncio, name) for name in
        ("create_task", "wait_for", "CancelledError", "TimeoutError", "Event")},
        get_running_loop=lambda: SimpleNamespace(time=lambda: next(clock)))
    monkeypatch.setattr(module, "asyncio", facade)
    stream = AsyncMock()
    stream.readline.side_effect = [json.dumps(frame).encode() for frame in frames] + [b""]
    async def launch():
        runtime.processes = (SimpleNamespace(stdout=stream), SimpleNamespace(returncode=None))
    monkeypatch.setattr(runtime, "launch", launch)
    monkeypatch.setattr(runtime, "cleanup", AsyncMock())
    async def exercise():
        run = await runtime.start({**SCENARIO, "duration": 1.5})
        await runtime.task
        result = runtime.get_run(run["id"])
        if recovers:
            assert result["status"] == "completed"
            assert [frame["t"] for frame in result["frames"]] == [0, 1, 1.5]
            assert result["score"]["falls"] == 0  # Startup falls never enter scored trajectory.
        else:
            assert result["status"] == "failed" and "未能站稳" in result["error"]
            assert result["frames"] == [] and result["score"] is None
    asyncio.run(exercise())


def test_run_history_sorts_creation_time_after_restart(runtime):
    runtime.save({'id': 'zz-older', 'created_at': 10, 'frames': []})
    runtime.save({'id': 'aa-newer', 'created_at': 20, 'frames': []})
    assert [r['id'] for r in OfficialRuntime(runtime.data_dir).list_runs()] == ['aa-newer', 'zz-older']


@pytest.mark.parametrize('enabled', [False, True])
def test_training_tuning_is_opt_in_and_recorded(tmp_path, monkeypatch, enabled):
    import tomllib
    monkeypatch.setenv('DUCKLAB_TRAINING_TUNING', '1' if enabled else '0')
    runtime = OfficialRuntime(tmp_path)
    policy = tomllib.loads(runtime.policy_config())['policy']
    if enabled:
        assert {key: policy[key] for key in ('action_scale', 'head_lowpass', 'legs_lowpass')} == {
            'action_scale': 1.0, 'head_lowpass': 1.0, 'legs_lowpass': 1.0}
        assert runtime.provenance()['profile'] == 'alpha-bam-training-v1'
    else:
        assert all(key not in policy for key in ('action_scale', 'head_lowpass', 'legs_lowpass'))
        assert runtime.provenance()['profile'] == 'alpha-walk-bam-v1'
    assert policy['walk'].endswith('/alpha_walking.onnx') and policy['stand'].endswith('/alpha_stand.onnx')


@pytest.mark.parametrize('yaw,start', [(0, [2, 3]), (90, [2, 3]), (-90, [-1, 4]), (180, [2, -2])])
def test_goal_is_relative_to_standing_pose_and_score_uses_world_target(runtime, monkeypatch, yaw, start):
    import math
    ready(monkeypatch, runtime)
    angle = math.radians(yaw)
    quaternion = [math.cos(angle / 2), 0, 0, math.sin(angle / 2)]
    target = [start[0] + math.cos(angle), start[1] + math.sin(angle)]
    frames = []
    for t, position in [(99.5, start), (100, start), (100.5, target), (101, target)]:
        frames.append({**world_frame(t), 'position': [*position, .2], 'quaternion': quaternion})
    clock = iter([0, 5, 5.6, 6.1, 6.6])
    facade = SimpleNamespace(**{name: getattr(asyncio, name) for name in
        ('create_task', 'wait_for', 'CancelledError', 'TimeoutError', 'Event')},
        get_running_loop=lambda: SimpleNamespace(time=lambda: next(clock)))
    monkeypatch.setattr(module, 'asyncio', facade)
    stream = AsyncMock()
    stream.readline.side_effect = [json.dumps(frame).encode() for frame in frames]
    async def launch():
        runtime.processes = (SimpleNamespace(stdout=stream), SimpleNamespace(returncode=None))
    monkeypatch.setattr(runtime, 'launch', launch)
    monkeypatch.setattr(runtime, 'cleanup', AsyncMock())
    async def exercise():
        run = await runtime.start(SCENARIO)
        await runtime.task
        result = runtime.get_run(run['id'])
        assert result['target'] == pytest.approx(target)
        assert result['start_pose'] == {'position': [*start, .2], 'quaternion': quaternion}
        assert result['versions']['target_frame'] == 'standing-body-relative'
        assert result['score']['success'] and result['score']['completion'] == pytest.approx(100)
        assert SCENARIO['target'] == [1, 0]
    asyncio.run(exercise())


def test_world_target_stays_fixed_after_rotated_standing(runtime, monkeypatch):
    ready(monkeypatch, runtime)
    clock = iter([0, 5, 5.5, 6])
    facade = SimpleNamespace(**{name: getattr(asyncio, name) for name in
        ('create_task', 'wait_for', 'CancelledError', 'TimeoutError', 'Event')},
        get_running_loop=lambda: SimpleNamespace(time=lambda: next(clock)))
    monkeypatch.setattr(module, 'asyncio', facade)
    frames = [world_frame(10), world_frame(10.5), world_frame(11.5)]
    rotated = [{**f, 'position': [2, 3, .2], 'quaternion': [math.sqrt(.5), 0, 0, math.sqrt(.5)]} for f in frames]
    stream = AsyncMock()
    stream.readline.side_effect = [json.dumps(f).encode() + b'\n' for f in rotated]
    async def launch():
        runtime.processes = (SimpleNamespace(stdout=stream), SimpleNamespace(returncode=None))
    monkeypatch.setattr(runtime, 'launch', launch)
    monkeypatch.setattr(runtime, 'cleanup', AsyncMock())
    async def exercise():
        scene = {**SCENARIO, 'target_frame': 'world'}
        run = await runtime.start(scene)
        await runtime.task
        assert runtime.get_run(run['id'])['target'] == scene['target']
        assert runtime.get_run(run['id'])['status'] == 'completed'
    asyncio.run(exercise())
