"""Run the original Pollen CLI against the current local scene."""
import json
import os
import sys
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
with urllib.request.urlopen("http://127.0.0.1:8765/api/status", timeout=3) as response:
    status = json.load(response)
if not status.get("socket"):
    raise SystemExit("请先在网页中开始一个场景。")
binary = PROJECT.parent / "vendor/microduck/target/debug/robotctl"
os.execv(str(binary), [str(binary), "--robot-socket", status["socket"], *sys.argv[1:]])
