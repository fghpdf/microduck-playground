import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from ducklab.protocol import rpc


def test_rpc_uses_official_ndjson_contract(tmp_path):
    async def scenario():
        state = tempfile.TemporaryDirectory(prefix='ducktest-', dir='/private/tmp')
        path = Path(state.name) / 'robot.sock'
        async def handler(reader, writer):
            msg = json.loads(await reader.readline())
            assert msg['method'] == 'robot.move'
            assert msg['params'] == {'vx': 0.15, 'vy': 0.0, 'vyaw': 0.0}
            writer.write((json.dumps({'jsonrpc': '2.0', 'id': msg['id'], 'result': {'accepted': True}}) + '\n').encode())
            await writer.drain()
            writer.close()
        server = await asyncio.start_unix_server(handler, str(path))
        try:
            assert await rpc(path, 'robot.move', {'vx': 0.15, 'vy': 0.0, 'vyaw': 0.0}) == {'accepted': True}
        finally:
            server.close()
            await server.wait_closed()
            state.cleanup()
    asyncio.run(scenario())


def test_missing_socket_reports_error(tmp_path):
    with pytest.raises(OSError):
        asyncio.run(rpc(tmp_path / 'missing.sock', 'robot.health', {}))
