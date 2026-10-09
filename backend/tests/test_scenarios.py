import math
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from ducklab.app import create_app
from ducklab.scenarios import SCENARIOS, get_scenario
from test_api import MissingRuntime

IDS = ['straight', 'turn', 'precision', 'long_straight', 'right_turn', 'shallow_left', 'shallow_right', 'wide_left', 'detour_left', 'detour_right', 'slalom', 'corridor', 'docking_bay', 'double_gate', 'island_route', 'diagonal_barrier', 'offset_gates', 'gentle_ramp', 'football_left', 'football_right', 'pickup_trash']


def test_scene_catalog_has_twenty_one_valid_independent_goals():
    assert [scene['id'] for scene in SCENARIOS] == IDS
    assert len({id(scene['target']) for scene in SCENARIOS}) == 21
    for scene in SCENARIOS:
        assert scene['name'] and scene['description']
        assert scene['duration'] > 0 and len(scene['target']) == 2
        assert all(math.isfinite(value) for value in scene['target'])
    assert get_scenario('long_straight')['target'] == [1.5, 0]
    assert get_scenario('right_turn')['target'] == [.65, -.65]
    assert get_scenario('shallow_left')['target'] == [.9, .35]
    assert get_scenario('shallow_right')['target'] == [.9, -.35]
    assert get_scenario('wide_left')['target'] == [.35, .9]


def test_lookup_returns_deep_copy_and_unknown_returns_none():
    returned = get_scenario('straight')
    returned['target'][0] = 999
    returned['name'] = 'changed'
    assert get_scenario('straight')['target'] == [.8, 0]
    assert get_scenario('straight')['name'] != 'changed'
    assert get_scenario('unknown') is None


@pytest.mark.parametrize('scene_id', IDS)
def test_api_accepts_every_catalog_scene(scene_id):
    runtime = MissingRuntime()
    runtime.start = AsyncMock(return_value={'id': 'test-run'})
    with TestClient(create_app(runtime)) as client:
        scene = get_scenario(scene_id)
        response = client.post('/api/runs', json={'scenario_id': scene_id, **({'mode': 'fast_reference'} if scene.get('fast_only') else {})})
    assert response.status_code == 201
    if scene.get('fast_only'):
        runtime.start.assert_awaited_once_with(scene, mode='fast_reference')
    else:
        runtime.start.assert_awaited_once_with(scene)


@pytest.mark.parametrize('scene_id', ['', 'a' * 65, 'unknown', '../etc', None, 42])
def test_invalid_scene_never_reaches_runtime(scene_id):
    runtime = MissingRuntime()
    runtime.start = AsyncMock()
    with TestClient(create_app(runtime)) as client:
        assert client.post('/api/runs', json={'scenario_id': scene_id}).status_code == 422
    runtime.start.assert_not_awaited()


def test_every_scene_has_consistent_difficulty_and_category():
    assert {scene['difficulty'] for scene in SCENARIOS} == {'simple', 'advanced', 'complex'}
    assert {scene['category'] for scene in SCENARIOS} == {'navigation', 'obstacle', 'terrain', 'football', 'pickup'}
    for scene in SCENARIOS:
        assert scene['category'] == (scene['task_type'] if scene.get('task_type') in ('football','pickup') else 'terrain' if scene.get('terrain') else 'obstacle' if scene.get('obstacles') else 'navigation')
        assert scene['difficulty'] in {'simple', 'advanced', 'complex'}
        if scene['category'] == 'navigation':
            assert scene['difficulty'] == 'simple'


@pytest.mark.parametrize('scene_id', IDS[11:17])
def test_new_obstacle_scenes_have_real_geometry_and_routes(scene_id):
    scene = get_scenario(scene_id)
    assert scene['target_frame'] == 'world'
    assert scene['obstacles'] and scene['waypoints']
    assert scene['waypoints'][-1] == scene['target']
    for obstacle in scene['obstacles']:
        assert len(obstacle['position']) == len(obstacle['size']) == 3
        assert all(math.isfinite(v) for v in obstacle['position'])
        assert all(math.isfinite(v) and v > 0 for v in obstacle['size'])
        assert math.isfinite(obstacle['yaw'])
    scene['obstacles'][0]['position'][0] = 999
    scene['waypoints'][0][0] = 999
    assert get_scenario(scene_id)['obstacles'][0]['position'][0] != 999
    assert get_scenario(scene_id)['waypoints'][0][0] != 999


def test_new_layouts_are_distinct():
    layouts = [repr(get_scenario(scene_id)['obstacles']) for scene_id in IDS[11:17]]
    assert len(set(layouts)) == 6
    assert get_scenario('diagonal_barrier')['obstacles'][0]['yaw'] != 0
