"""An external program using the same official IPC as robotctl.

Start a scene in the web UI first, then run `.venv/bin/python examples/drive.py`.
The bridge records this program's movement without routing it through the UI.
"""
import asyncio
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from ducklab.protocol import rpc


async def main():
    with urllib.request.urlopen("http://127.0.0.1:8765/api/status", timeout=3) as response:
        status = json.load(response)
    if not status.get("socket"):
        raise SystemExit("请先在网页中开始一个场景，并等待机器人站稳。")
    path = Path(status["socket"])
    print("通过官方控制接口前进 5 秒…")
    try:
        for _ in range(50):
            await rpc(path, "robot.move", {"vx": 0.3, "vy": 0.0, "vyaw": 0.0})
            await asyncio.sleep(0.1)
    finally:
        await rpc(path, "robot.move", {"vx": 0.0, "vy": 0.0, "vyaw": 0.0})
    print("已停车。网页中停止并保存即可回放。")


if __name__ == "__main__":
    asyncio.run(main())
