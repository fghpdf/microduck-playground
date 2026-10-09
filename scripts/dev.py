"""Start both local services; stop only the processes this launcher owns."""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


def main():
    python = PROJECT / ".venv/bin/python"
    if not python.exists() or not (PROJECT / "web/node_modules").exists():
        raise SystemExit("请先运行 scripts/setup.sh，准备本地依赖。")
    for port in (8765, 5173):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                raise SystemExit(f"端口 {port} 已在使用，请先关闭原来的本地服务。")
    children = []
    try:
        env = {**os.environ, "PYTHONPATH": str(PROJECT / "backend")}
        children.append(subprocess.Popen([str(python), "-m", "uvicorn", "ducklab.app:app",
                                         "--host", "127.0.0.1", "--port", "8765"], cwd=PROJECT, env=env))
        children.append(subprocess.Popen(["npm", "run", "dev", "--", "--strictPort"], cwd=PROJECT / "web"))
        print("\n本地实验室：http://127.0.0.1:5173\n按 Ctrl+C 关闭网站和仿真。", flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        # Let the backend's lifespan stop the official native processes.
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    main()
