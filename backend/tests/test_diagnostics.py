import asyncio
from unittest.mock import AsyncMock

import pytest

from ducklab.diagnostics import Diagnostics


@pytest.mark.parametrize('reply,error,accepted', [({'accepted': True}, None, True),
    ({'accepted': False}, None, False), (None, RuntimeError('connection lost'), None)])
def test_command_logs_response_or_failure_without_hiding_it(reply, error, accepted):
    rpc = AsyncMock(return_value=reply, side_effect=error)
    recorder = Diagnostics('/fake/socket', rpc)
    async def exercise():
        if error:
            with pytest.raises(RuntimeError, match='connection lost'):
                await recorder.command(.2, -.3)
        else:
            assert await recorder.command(.2, -.3) == reply
        await recorder.close()
    asyncio.run(exercise())
    entry = recorder.snapshot()['commands'][0]
    assert entry['vx'] == .2 and entry['vyaw'] == -.3
    assert entry['accepted'] is accepted
    assert entry['sent_at'] > 0 and entry['duration_ms'] >= 0
    assert entry['error'] == ('connection lost' if error else None)


def test_health_failure_does_not_block_commands_and_recovers():
    sampled = asyncio.Event()
    calls = 0
    async def rpc(path, method, params, **kwargs):
        nonlocal calls
        if method == 'robot.policies':
            return {'homed': True, 'sitting': False, 'enabled': True}
        if method == 'robot.move':
            return {'accepted': True}
        calls += 1
        if calls == 1:
            raise RuntimeError('health unavailable')
        sampled.set()
        return {'healthy': True, 'control_loop': {'target_hz': 50, 'achieved_hz': None}}
    recorder = Diagnostics('/fake/socket', rpc, interval=.001)
    async def exercise():
        recorder.start()
        assert await recorder.command(.1, 0) == {'accepted': True}
        await asyncio.wait_for(sampled.wait(), 1)
        await recorder.close()
    asyncio.run(exercise())
    assert recorder.snapshot()['health'][0]['error'] == 'health unavailable'
    assert recorder.snapshot()['health'][1]['result']['control_loop']['achieved_hz'] is None
    assert len(recorder.snapshot()['commands']) == 1
    assert recorder.snapshot()['health'][1]['state']['sitting'] is False
    assert recorder.snapshot()['health'][1]['sim_time'] is None
    assert recorder.snapshot()['health'][1]['elapsed'] >= 0


def test_close_waits_for_inflight_command_even_when_caller_is_cancelled():
    entered = asyncio.Event()
    release = asyncio.Event()
    async def rpc(*args, **kwargs):
        entered.set()
        await release.wait()
        return {'accepted': True}
    recorder = Diagnostics('/fake/socket', rpc)
    async def exercise():
        caller = asyncio.create_task(recorder.command(.3, 0))
        await entered.wait()
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        closing = asyncio.create_task(recorder.close())
        await asyncio.sleep(0)
        assert not closing.done()
        release.set()
        await closing
    asyncio.run(exercise())
    assert recorder.snapshot()['commands'][0]['accepted'] is True


def test_completed_run_waits_for_command_and_preserves_trace_in_saved_playback(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    from ducklab import runtime as module
    from ducklab.runtime import OfficialRuntime
    runtime = OfficialRuntime(tmp_path)
    monkeypatch.setattr(runtime, 'status', lambda: {'available': True})
    clock = iter([0, 5, 5.6, 6.6])
    facade = SimpleNamespace(**{name: getattr(asyncio, name) for name in
        ('create_task', 'wait_for', 'CancelledError', 'TimeoutError', 'Event', 'shield')},
        get_running_loop=lambda: SimpleNamespace(time=lambda: next(clock)))
    monkeypatch.setattr(module, 'asyncio', facade)
    command_entered, command_release, running = asyncio.Event(), asyncio.Event(), asyncio.Event()
    frame_index = 0
    async def read():
        nonlocal frame_index
        frame_index += 1
        if frame_index == 3:
            running.set()
            await command_entered.wait()
        frame = {'type': 'frame', 't': float(frame_index), 'position': [0, 0, .2],
                 'quaternion': [1, 0, 0, 0], 'joints': [], 'fallen': False, 'collisions': 0}
        return json.dumps(frame).encode()
    async def launch():
        runtime.processes = (SimpleNamespace(stdout=SimpleNamespace(readline=read)),
                             SimpleNamespace(returncode=None))
    async def rpc(path, method, params, **kwargs):
        if method == 'robot.move':
            command_entered.set()
            await command_release.wait()
            return {'accepted': True}
        return {'healthy': True}
    monkeypatch.setattr(module, 'rpc', rpc)
    monkeypatch.setattr(runtime, 'launch', launch)
    monkeypatch.setattr(runtime, 'cleanup', AsyncMock())
    async def exercise():
        run = await runtime.start({'id': 'test', 'target': [1, 0], 'duration': 1})
        await running.wait()
        command = asyncio.create_task(runtime.control(.2, .1))
        await command_entered.wait()
        await asyncio.sleep(0)
        assert not runtime.task.done()  # Finalization awaits the pending control reply.
        command_release.set()
        await command
        await runtime.task
        saved = OfficialRuntime(tmp_path).get_run(run['id'])
        assert saved['status'] == 'completed'
        assert saved['diagnostics']['commands'][0]['accepted'] is True
        assert saved['score'] == runtime.get_run(run['id'])['score']
    asyncio.run(exercise())


def test_policy_poll_failure_is_retained_as_diagnostic():
    sampled = asyncio.Event()
    async def rpc(path, method, params, **kwargs):
        if method == 'robot.policies':
            sampled.set()
            raise RuntimeError('policies unavailable')
        return {'healthy': False, 'reason': 'slow control'}
    recorder = Diagnostics('/fake/socket', rpc, sim_time=lambda: 2.5)
    async def exercise():
        recorder.start()
        await sampled.wait()
        await recorder.close()
    asyncio.run(exercise())
    sample = recorder.snapshot()['health'][0]
    assert sample['result']['healthy'] is False
    assert sample['state'] is None and sample['state_error'] == 'policies unavailable'
    assert sample['sim_time'] == 2.5
