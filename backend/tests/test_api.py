from fastapi.testclient import TestClient

from ducklab.app import create_app


class MissingRuntime:
    def status(self):
        return {"available": False, "detail": "官方运行环境尚未准备好", "backend": "official"}

    async def start(self, scenario):
        raise RuntimeError("官方运行环境尚未准备好")

    def list_runs(self):
        return []

    def get_run(self, run_id):
        return None

    async def close(self):
        pass


def client():
    return TestClient(create_app(MissingRuntime()))


def test_status_and_scenarios():
    with client() as c:
        assert c.get('/api/status').json()['available'] is False
        scenes = c.get('/api/scenarios').json()
        assert len(scenes) == 21
        assert {scene["difficulty"] for scene in scenes} == {"simple", "advanced", "complex"}
        assert {scene["category"] for scene in scenes} == {"navigation", "obstacle", "terrain", "football", "pickup"}
        assert all(len(s['target']) == 2 for s in scenes)


def test_unavailable_runtime_never_creates_a_fake_run():
    with client() as c:
        assert c.post('/api/runs', json={'scenario_id': 'straight'}).status_code == 503
        assert c.get('/api/runs').json() == []


def test_reject_unknown_scene_and_invalid_controls():
    with client() as c:
        assert c.post('/api/runs', json={'scenario_id': '../etc'}).status_code == 422
        for control in ({'vx': 1, 'vyaw': 0}, {'vx': 0, 'vyaw': 2}, {'vx': 'nan', 'vyaw': 0}):
            assert c.post('/api/control', json=control).status_code == 422


def test_reject_cross_origin_mutation_and_unknown_host():
    with client() as c:
        assert c.post('/api/runs', headers={'Origin': 'https://evil.example'}, json={'scenario_id': 'straight'}).status_code == 403
        assert c.get('/api/status', headers={'Host': 'evil.example'}).status_code == 400


def test_missing_run_returns_404():
    with client() as c:
        assert c.get('/api/runs/no-such-run').status_code == 404
