from types import SimpleNamespace
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from ducklab.app import create_app


def test_skill_endpoint_validates_names_and_dispatches():
    runner=SimpleNamespace(skill=AsyncMock(return_value={'accepted':True}),close=AsyncMock())
    with TestClient(create_app(runner)) as c:
        assert c.post('/api/skill',json={'name':'kick_left'}).status_code==200
        runner.skill.assert_awaited_once_with('kick_left')
        assert c.post('/api/skill',json={'name':'unknown'}).status_code==422
        assert c.post('/api/skill',json={'name':'ground_pick','command':'arbitrary'}).status_code==422
