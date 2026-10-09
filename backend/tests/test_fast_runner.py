import math
import pytest
from ducklab.fast_runner import navigate, world_target, run_steps


def test_target_rotates_relative_to_standing_heading():
    assert world_target([1, 2, .12], [math.sqrt(.5), 0, 0, math.sqrt(.5)], [.8, 0]) == pytest.approx([1, 2.8])


def test_navigator_turns_both_directions_and_stops_at_goal():
    assert navigate([0, 0], [1, 0, 0, 0], [1, 1]) == (.3, .5)
    assert navigate([0, 0], [1, 0, 0, 0], [1, -1]) == (.3, -.5)
    assert navigate([.95, 0], [1, 0, 0, 0], [1, 0]) == (0, 0)


def test_fixed_steps_record_simulation_time_and_settle():
    state = {'ticks': 0}
    commands = []
    def step(command):
        commands.append(command)
        state['ticks'] += 1
        return {'position': [.1 if state['ticks'] < 3 else .95, 0, .12],
                'quaternion': [1, 0, 0, 0], 'joints': [], 'fallen': False, 'collisions': 0}
    frames = list(run_steps(step, [1, 0], 10))
    assert frames[0]['t'] == .02
    assert frames[-1]['t'] == pytest.approx(.66)
    assert len(frames) == 33
    assert commands[-1] == (0, 0)


def test_fall_finishes_early_and_duration_is_hard_limit():
    def fallen(_):
        return {'position': [0, 0, .01], 'quaternion': [1, 0, 0, 0], 'fallen': True}
    assert len(list(run_steps(fallen, [1, 0], 5))) == 1
    def still(_):
        return {'position': [0, 0, .12], 'quaternion': [1, 0, 0, 0], 'fallen': False}
    assert len(list(run_steps(still, [1, 0], .1))) == 5


def test_offline_runner_records_real_physics_with_normal_speed_timestamps(monkeypatch, capsys):
    """Exercise the installed official CPU policy/BAM path without wall pacing."""
    import json
    from pathlib import Path
    import sys
    from ducklab.fast_runner import main
    from ducklab.scoring import score_run
    root = Path(__file__).resolve().parents[2]
    monkeypatch.setattr(sys, 'argv', ['fast_runner', '--rl', str(root.parent / 'vendor/microduck_rl'),
                                    '--policies', str(root / 'data/policies/current'), '--scenario', 'precision'])
    main()
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert records[0]['provenance']['controller'] == 'reference-navigation'
    assert records[0]['provenance']['initial_condition'] == 'official-STAND2'
    frames = [record for record in records if record['type'] == 'frame']
    assert frames[0]['t'] == 0
    assert frames[1]['t'] == .02
    assert records[-1]['type'] == 'done'
    assert score_run(frames, records[0]['target'])['success']
    assert frames[-1]['position'][0] > frames[0]['position'][0] + .2


def test_unknown_scene_fails_before_loading_physics(monkeypatch):
    import sys
    from ducklab.fast_runner import main
    monkeypatch.setattr(sys, 'argv', ['fast_runner', '--rl', '/missing', '--policies', '/missing', '--scenario', 'unknown'])
    with pytest.raises(SystemExit, match='2'):
        main()


def test_navigator_starts_from_actual_warmup_heading():
    commands = []
    initial = {'position': [3, 4, .12], 'quaternion': [math.sqrt(.5), 0, 0, math.sqrt(.5)]}
    def step(command):
        commands.append(command)
        return {**initial, 'fallen': False}
    list(run_steps(step, [3, 5], .02, initial=initial))
    assert commands == [pytest.approx((.3, 0))]


def test_waypoint_navigation_keeps_moving_until_final_goal():
    commands = []
    initial = {'position': [0, 0, .12], 'quaternion': [1, 0, 0, 0]}
    def step(command):
        commands.append(command)
        return {**initial, 'position': [.5, 0, .12], 'fallen': False}
    list(run_steps(step, [1, 0], .06, initial=initial, waypoints=[[.5, 0]]))
    assert all(command[0] == .3 for command in commands)
