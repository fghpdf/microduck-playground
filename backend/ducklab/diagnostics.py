"""Best-effort official health sampling and durable control request traces."""
import asyncio
import time


class Diagnostics:
    def __init__(self, socket, rpc, interval=1.0, sim_time=lambda: None):
        self.socket = socket
        self.rpc = rpc
        self.interval = interval
        self.sim_time = sim_time
        self.started = time.perf_counter()
        self.commands = ()
        self.health = ()
        self.pending = ()
        self.sampler = None

    def snapshot(self):
        return {"commands": list(self.commands), "health": list(self.health)}

    def start(self):
        self.sampler = asyncio.create_task(self._sample())

    async def command(self, vx, vyaw):
        task = asyncio.create_task(self._command(vx, vyaw))
        self.pending = (*self.pending, task)
        return await asyncio.shield(task)

    async def _command(self, vx, vyaw):
        sent_at, started = time.time(), time.perf_counter()
        accepted, error = None, None
        try:
            result = await self.rpc(self.socket, "robot.move", {"vx": vx, "vy": 0.0, "vyaw": vyaw})
            accepted = isinstance(result, dict) and result.get("accepted") is True
            return result
        except Exception as failure:
            error = str(failure)
            raise
        finally:
            self.commands = (*self.commands, {"sent_at": sent_at, "duration_ms": round(
                (time.perf_counter() - started) * 1000, 3), "vx": vx, "vyaw": vyaw,
                "accepted": accepted, "error": error})
            self.pending = tuple(task for task in self.pending if task is not asyncio.current_task())

    async def _sample(self):
        while True:
            sampled_at, started = time.time(), time.perf_counter()
            result, error = None, None
            state, state_error = None, None
            try:
                result = await self.rpc(self.socket, "robot.health", {}, timeout=.75)
            except Exception as failure:
                error = str(failure)
            try:
                state = await self.rpc(self.socket, "robot.policies", {}, timeout=.75)
            except Exception as failure:
                state_error = str(failure)
            self.health = (*self.health, {"sampled_at": sampled_at, "duration_ms": round(
                (time.perf_counter() - started) * 1000, 3), "result": result, "error": error, "state": state, "state_error": state_error,
                "sim_time": self.sim_time(), "elapsed": round(time.perf_counter() - self.started, 6)})
            await asyncio.sleep(self.interval)

    async def close(self):
        if self.sampler:
            self.sampler.cancel()
            await asyncio.gather(self.sampler, return_exceptions=True)
            self.sampler = None
        await asyncio.gather(*self.pending, return_exceptions=True)
