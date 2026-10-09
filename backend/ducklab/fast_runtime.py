"""Subprocess lifecycle for accelerated reference-policy evaluation."""
import asyncio
import json
import sys
import time

from .scoring import score_run
from .skill_scoring import score_scene


class FastRuntimeMixin:
    async def launch_fast(self, scenario):
        from .runtime import RL
        directory = self.data_dir / 'logs'
        directory.mkdir(parents=True, exist_ok=True)
        self.log = (directory / f'{self.active}.log').open('wb')
        process = await asyncio.create_subprocess_exec(
            sys.executable, '-m', 'ducklab.fast_runner', '--rl', str(RL),
            '--policies', str(self.policy_dir), '--scenario', scenario['id'],
            stdout=asyncio.subprocess.PIPE, stderr=self.log)
        self.processes = (process,)
        return process

    async def execute_fast(self, run_id, scenario):
        started = time.monotonic()
        run = self.runs[run_id]
        ready = False
        try:
            process = await self.launch_fast(scenario)
            finished = False
            while not self.stop_event.is_set():
                line = await asyncio.wait_for(process.stdout.readline(), 30)
                if not line:
                    raise RuntimeError('快速仿真提前退出，请查看本次运行日志')
                if not line.startswith(b'{'):
                    continue
                message = json.loads(line)
                if message['type'] == 'ready':
                    ready = True
                    run = {**run, 'status': 'running', 'target': message['target'],
                           'start_pose': message['start_pose'], 'objects': message.get('objects', run.get('objects', [])),
                           'versions': {**run['versions'], **message.get('provenance', {})}}
                elif message['type'] == 'frame':
                    if not ready:
                        raise RuntimeError('快速仿真尚未就绪')
                    run = {**run, 'frames': [*run['frames'], message]}
                elif message['type'] == 'done':
                    if not ready or not run['frames']:
                        raise RuntimeError('快速仿真未生成轨迹')
                    if await asyncio.wait_for(process.wait(), 5) != 0:
                        raise RuntimeError('快速仿真异常退出')
                    finished = True
                    break
                self.runs = {**self.runs, run_id: run}
            run = {**run, 'status': 'completed' if finished else 'stopped',
                   'score': score_scene(run['frames'], scenario, run['target'])}
        except asyncio.CancelledError:
            run = {**self.runs[run_id], 'status': 'stopped',
                   'score': score_scene(self.runs[run_id]['frames'], scenario, self.runs[run_id]['target'])}
        except Exception as error:
            run = {**self.runs[run_id], 'status': 'failed', 'error': str(error), 'score': None}
        finally:
            run = {**run, 'wall_duration': round(time.monotonic() - started, 3)}
            try:
                await self.cleanup()
                self.save(run)
            except OSError as error:
                self.runs = {**self.runs, run_id: {**run, 'status': 'failed', 'error': f'记录保存失败：{error}'}}
            finally:
                self.active = None
