from pathlib import Path
import mujoco
import pytest
from ducklab.scenarios import get_scenario
from ducklab.scene_geometry import add_obstacles
from ducklab.bam_body import create_body


def test_boxes_have_full_size_contract_and_collide():
    spec = mujoco.MjSpec()
    add_obstacles(spec, {'obstacles': [{'position': [1, 2, .15], 'size': [.3, .4, .3], 'yaw': 0}]})
    model = spec.compile()
    assert model.geom_pos[0] == pytest.approx([1, 2, .15])
    assert model.geom_size[0] == pytest.approx([.15, .2, .15])
    assert model.geom_contype[0] and model.geom_conaffinity[0]


def test_obstacles_are_in_real_robot_model():
    root = Path(__file__).resolve().parents[3]
    scene = get_scenario('detour_left')
    world, _ = create_body(root / 'vendor/microduck_rl', scene)
    index = mujoco.mj_name2id(world.model, mujoco.mjtObj.mjOBJ_GEOM, 'ducklab_obstacle_0')
    assert index >= 0
    assert world.model.geom_pos[index] == pytest.approx(scene['obstacles'][0]['position'])


def test_scene_geometry_rejects_invalid_boxes():
    with pytest.raises(ValueError):
        add_obstacles(mujoco.MjSpec(), {'obstacles': [{'position': [0, 0, 0], 'size': [0, 1, 1], 'yaw': 0}]})


@pytest.mark.parametrize('scene_id', ['detour_left', 'detour_right', 'slalom'])
def test_reference_navigation_completes_real_obstacle_routes(scene_id):
    from ducklab.fast_runner import create_stepper, run_steps
    from ducklab.scoring import score_run
    root = Path(__file__).resolve().parents[3]
    scene = get_scenario(scene_id)
    step = create_stepper(root / 'vendor/microduck_rl', root / 'microduck-local/data/policies/current', scene)
    for _ in range(50):
        initial = step((0, 0))
    frames = [{**initial, 't': 0}, *run_steps(step, scene['target'], scene['duration'], initial=initial,
                                            waypoints=scene['waypoints'])]
    result = score_run(frames, scene['target'])
    assert result['success'] and result['falls'] == 0 and result['collisions'] == 0


def test_straight_drive_into_box_records_real_contact():
    from ducklab.fast_runner import create_stepper
    root = Path(__file__).resolve().parents[3]
    step = create_stepper(root / 'vendor/microduck_rl', root / 'microduck-local/data/policies/current',
                          get_scenario('detour_left'))
    for _ in range(50):
        step((0, 0))
    frames = [step((.3, 0)) for _ in range(800)]
    assert any(frame['collisions'] > 0 for frame in frames)


def test_legacy_mode_rejects_obstacles_before_loading_physics(monkeypatch):
    import sys
    from ducklab.body_runner import main
    monkeypatch.setattr(sys, 'argv', ['body_runner', '--rl', '/missing', '--port', '1234',
                                    '--legacy', '--scenario', 'detour_left'])
    with pytest.raises(SystemExit, match='2'):
        main()


def test_ramp_is_sloped_collidable_terrain_in_robot_model():
    root = Path(__file__).resolve().parents[3]
    scene = get_scenario('gentle_ramp')
    assert scene and scene['category'] == 'terrain'
    world, _ = create_body(root / 'vendor/microduck_rl', scene)
    geom = mujoco.mj_name2id(world.model, mujoco.mjtObj.mjOBJ_GEOM, 'ducklab_terrain_0')
    assert geom >= 0
    assert world.model.geom_contype[geom] and geom not in world.obstacle_geoms
    mesh = world.model.geom_dataid[geom]
    vertices = world.model.mesh_vert[world.model.mesh_vertadr[mesh]:world.model.mesh_vertadr[mesh] + world.model.mesh_vertnum[mesh]]
    assert len(vertices) == 6


def test_ramp_navigation_crosses_peak_without_falls_or_collision_penalty():
    from ducklab.fast_runner import create_stepper, run_steps
    from ducklab.scoring import score_run
    root = Path(__file__).resolve().parents[3]
    scene = get_scenario('gentle_ramp')
    step = create_stepper(root / 'vendor/microduck_rl', root / 'microduck-local/data/policies/current', scene)
    for _ in range(50):
        initial = step((0, 0))
    frames = [{**initial, 't': 0}, *run_steps(step, scene['target'], scene['duration'], initial=initial,
                                            waypoints=scene['waypoints'])]
    result = score_run(frames, scene['target'])
    assert result['success'] and result['falls'] == 0 and result['collisions'] == 0
    assert max(frame['position'][2] for frame in frames) > initial['position'][2] + .035


@pytest.mark.parametrize('change', [{'direction': 0}, {'kind': 'unknown'}, {'size': [.8, .8, 0]},
                                   {'position': [float('nan'), 0, 0]}])
def test_invalid_terrain_fails_before_compilation(change):
    ramp = {**get_scenario('gentle_ramp')['terrain'][0], **change}
    with pytest.raises(ValueError, match='invalid ramp terrain'):
        add_obstacles(mujoco.MjSpec(), {'terrain': [ramp]})


def test_ramp_faces_match_declared_peak_and_width():
    import numpy as np
    scene = get_scenario('gentle_ramp')
    spec = mujoco.MjSpec()
    add_obstacles(spec, scene)
    model = spec.compile()
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    for geom, ramp in enumerate(scene['terrain']):
        mesh = model.geom_dataid[geom]
        start = model.mesh_vertadr[mesh]
        vertices = model.mesh_vert[start:start + model.mesh_vertnum[mesh]]
        world = vertices @ data.geom_xmat[geom].reshape(3, 3).T + data.geom_xpos[geom]
        assert np.max(world[:, 2]) == pytest.approx(.06, abs=1e-7)
        high_vertices = world[world[:, 2] > .059]
        assert high_vertices[:, 0] == pytest.approx([1.2, 1.2], abs=1e-7)
        assert sorted(high_vertices[:, 1]) == pytest.approx([-.4, .4], abs=1e-7)
