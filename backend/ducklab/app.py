import time
from typing import Literal
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .runtime import OfficialRuntime
from .scenarios import SCENARIOS, get_scenario


class StartRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["realtime", "fast_reference"] = "realtime"
    scenario_id: str = Field(min_length=1, max_length=64)

    @field_validator("scenario_id")
    @classmethod
    def known_scenario(cls, value):
        if get_scenario(value) is None:
            raise ValueError("未知场景")
        return value


class Skill(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["kick_left", "kick_right", "ground_pick"]


class Control(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    vx: float = Field(ge=-0.3, le=0.3)
    vyaw: float = Field(ge=-1.5, le=1.5)


def create_app(runtime=None):
    runner = runtime if runtime is not None else OfficialRuntime()

    @asynccontextmanager
    async def lifespan(app):
        yield
        await runner.close()

    app = FastAPI(title="Microduck Local Lab", lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])
    requests = {}

    @app.middleware("http")
    async def protect_local(request: Request, call_next):
        origin = request.headers.get("origin")
        allowed = {"http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8765", "http://127.0.0.1:8765"}
        if request.method != "GET" and origin is not None and origin not in allowed:
            return JSONResponse({"detail": "仅允许本地页面控制机器人"}, status_code=403)
        now = time.monotonic()
        key = request.client.host if request.client else "local"
        recent = [t for t in requests.get(key, ()) if now - t < 1]
        if len(recent) >= 60:
            return JSONResponse({"detail": "请求过于频繁"}, status_code=429)
        requests[key] = [*recent, now]
        return await call_next(request)

    @app.get("/api/status")
    def status():
        return runner.status()

    @app.get("/api/scenarios")
    def scenarios():
        return [get_scenario(scene["id"]) for scene in SCENARIOS]

    @app.get("/api/runs")
    def runs():
        return runner.list_runs()

    @app.post("/api/runs", status_code=201)
    async def start(body: StartRun):
        try:
            scenario = get_scenario(body.scenario_id)
            if body.mode == "fast_reference":
                return await runner.start(scenario, mode=body.mode)
            return await runner.start(scenario)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        except RuntimeError as error:
            raise HTTPException(503, str(error)) from error

    @app.get("/api/runs/{run_id}")
    def run(run_id: str):
        result = runner.get_run(run_id)
        if result is None:
            raise HTTPException(404, "找不到该运行记录")
        return result

    @app.post("/api/runs/{run_id}/stop")
    async def stop(run_id: str):
        try:
            return await runner.stop(run_id)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @app.post("/api/control")
    async def control(body: Control):
        try:
            return await runner.control(body.vx, body.vyaw)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        except (OSError, RuntimeError, TimeoutError) as error:
            raise HTTPException(503, "控制服务暂时不可用，请停止本次运行并查看日志") from error

    @app.post("/api/skill")
    async def skill(body: Skill):
        try:
            return await runner.skill(body.name)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        except (OSError, RuntimeError, TimeoutError) as error:
            raise HTTPException(503, "控制服务暂时不可用") from error

    return app


app = create_app()
