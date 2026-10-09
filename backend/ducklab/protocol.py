import asyncio
import json
from pathlib import Path


async def rpc(path: Path, method: str, params: dict, timeout: float = 3.0):
    """Use the official robotd Unix-socket NDJSON JSON-RPC protocol."""
    reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(str(path)), timeout)
    try:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        writer.write((json.dumps(payload, allow_nan=False) + "\n").encode())
        await writer.drain()
        async with asyncio.timeout(timeout):
            while line := await reader.readline():
                answer = json.loads(line)
                if answer.get("id") != 1:
                    continue
                if "error" in answer:
                    raise RuntimeError(f"官方控制接口拒绝请求：{answer['error']}")
                return answer.get("result")
        raise RuntimeError("官方控制服务关闭了连接")
    finally:
        writer.close()
        await writer.wait_closed()
