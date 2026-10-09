import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from ducklab.app import create_app
from ducklab.runtime import OfficialRuntime

SCENE = {'id': 'straight', 'target': [.8, 0], 'duration': 30}


def test_fast_stream_simulated_time_and_persistence(tmp_path, monkeypatch):
    runner = OfficialRuntime(tmp_path)
    monkeypatch.setattr(runner, 'status', lambda: {'available': True})
    messages = [{'type': 'ready', 'target': [.8, 0], 'start_pose': {}},
                *[{'type': 'frame', 't': t, 'position': [.8, 0, .15],
                   'quaternion': [1, 0, 0, 0], 'joints': [], 'fallen': False,
                   'collisions': 0} for t in [0, .5, 30]], {'type': 'done'}]
    stream = AsyncMock()
    stream.readline.side_effect = [json.dumps(m).encode() + b'\n' for m in messages]
    proc = SimpleNamespace(stdout=stream, returncode=0, wait=AsyncMock(return_value=0))
    monkeypatch.setattr(runner, 'launch_fast', AsyncMock(return_value=proc), raising=False)
    monkeypatch.setattr(runner, 'cleanup', AsyncMock())
    async def exercise():
        run = await runner.start(SCENE, mode='fast_reference')
        await runner.task
        result = runner.get_run(run['id'])
        assert result['status'] == 'completed'
        assert result['mode'] == 'fast_reference'
        assert result['versions']['controller'] == 'reference-navigation'
        assert result['score']['duration'] == 30
        assert result['wall_duration'] < 2
        assert result['score']['success']
        assert runner.active is None
        assert OfficialRuntime(tmp_path).get_run(run['id']) == result
    asyncio.run(exercise())


def test_fast_eof_is_failure(tmp_path, monkeypatch):
    runner = OfficialRuntime(tmp_path)
    monkeypatch.setattr(runner, 'status', lambda: {'available': True})
    proc = SimpleNamespace(stdout=SimpleNamespace(readline=AsyncMock(return_value=b'')))
    monkeypatch.setattr(runner, 'launch_fast', AsyncMock(return_value=proc), raising=False)
    monkeypatch.setattr(runner, 'cleanup', AsyncMock())
    async def exercise():
        run = await runner.start(SCENE, mode='fast_reference')
        await runner.task
        assert runner.get_run(run['id'])['status'] == 'failed'
        assert runner.get_run(run['id'])['score'] is None
        assert runner.active is None
    asyncio.run(exercise())


def test_fast_request_validated_and_dispatched():
    runner = SimpleNamespace(start=AsyncMock(return_value={'id': 'fast'}), close=AsyncMock())
    with TestClient(create_app(runner)) as client:
        assert client.post('/api/runs', json={'scenario_id': 'straight', 'mode': 'fast_reference'}).status_code == 201
        assert runner.start.await_args.kwargs == {'mode': 'fast_reference'}
        assert client.post('/api/runs', json={'scenario_id': 'straight', 'mode': 'turbo'}).status_code == 422


def test_fast_stop_before_launch_finishes_and_controls_are_rejected(tmp_path, monkeypatch):
    runner = OfficialRuntime(tmp_path)
    monkeypatch.setattr(runner, 'status', lambda: {'available': True})
    entered = asyncio.Event()
    release = asyncio.Event()
    async def launch(scene):
        entered.set()
        await release.wait()
        return SimpleNamespace()
    monkeypatch.setattr(runner, 'launch_fast', launch)
    monkeypatch.setattr(runner, 'cleanup', AsyncMock())
    async def exercise():
        run = await runner.start(SCENE, mode='fast_reference')
        await entered.wait()
        runner.runs = {**runner.runs, run['id']: {**runner.runs[run['id']], 'status': 'running'}}
        import pytest
        with pytest.raises(ValueError, match='内置导航'):
            await runner.control(.3, 0)
        stop = asyncio.create_task(runner.stop(run['id']))
        await asyncio.sleep(0)
        release.set()
        result = await stop
        assert result['status'] == 'stopped'
        assert runner.active is None
    asyncio.run(exercise())


def test_fast_immediate_stop_and_save_error_clear_active(tmp_path, monkeypatch):
    runner = OfficialRuntime(tmp_path)
    monkeypatch.setattr(runner, 'status', lambda: {'available': True})
    async def launch(scene):
        await asyncio.Event().wait()
    monkeypatch.setattr(runner, 'launch_fast', launch)
    monkeypatch.setattr(runner, 'cleanup', AsyncMock())
    def fail_save(run):
        raise OSError('disk full')
    monkeypatch.setattr(runner, 'save', fail_save)
    async def exercise():
        run = await runner.start(SCENE, mode='fast_reference')
        result = await runner.stop(run['id'])
        assert result['status'] == 'failed'
        assert '记录保存失败' in result['error']
        assert runner.active is None
    asyncio.run(exercise())


def test_obstacle_layout_and_world_target_are_preserved(tmp_path, monkeypatch):
    runner = OfficialRuntime(tmp_path)
    monkeypatch.setattr(runner, 'status', lambda: {'available': True})
    async def launch(scene):
        await asyncio.Event().wait()
    monkeypatch.setattr(runner, 'launch_fast', launch)
    monkeypatch.setattr(runner, 'cleanup', AsyncMock())
    scene = {**SCENE, 'difficulty': 'complex', 'category': 'obstacle', 'terrain': [{'kind': 'ramp', 'position': [.8, 0, 0], 'size': [.8, .8, .06], 'direction': 1}], 'target_frame': 'world', 'obstacles': [
        {'position': [.5, 0, .15], 'size': [.2, .2, .3], 'yaw': 0}]}
    async def exercise():
        run = await runner.start(scene, mode='fast_reference')
        assert run['difficulty'] == 'complex' and run['category'] == 'obstacle'
        assert run['terrain'] == scene['terrain']
        assert run['scenario_snapshot']['target'] == scene['target']
        assert run['obstacles'] == scene['obstacles']
        assert run['versions']['target_frame'] == 'world'
        assert run['versions']['scene'] == 'terrain-v1'
        scene['obstacles'][0]['position'][0] = 999
        assert run['obstacles'][0]['position'][0] == .5
        await runner.stop(run['id'])
    asyncio.run(exercise())


def test_fast_only_scene_cannot_start_native_mode(tmp_path, monkeypatch):
    import pytest
    runner = OfficialRuntime(tmp_path)
    monkeypatch.setattr(runner, 'status', lambda: {'available': True})
    monkeypatch.setattr(runner, 'launch', AsyncMock(side_effect=RuntimeError('mock launch')))
    async def exercise():
        with pytest.raises(ValueError, match='快速试跑'):
            await runner.start({**SCENE, 'fast_only': True})
        assert runner.active is None
    asyncio.run(exercise())
