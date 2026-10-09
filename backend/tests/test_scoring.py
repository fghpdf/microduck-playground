import math

import pytest

from ducklab.scoring import score_run


def frame(t, x=0, y=0, *, fallen=False, collisions=0):
    return {"t": t, "position": [x, y, 0.2], "quaternion": [1, 0, 0, 0],
            "joints": [], "fallen": fallen, "collisions": collisions}


def test_empty_run():
    assert score_run([], [1, 0]) == {
        "success": False, "completion": 0.0, "duration": 0.0,
        "falls": 0, "collisions": 0,
    }


def test_reaches_target_and_holds_for_half_second():
    result = score_run([frame(3), frame(4, 1), frame(4.5, 1)], [1, 0])
    assert result == {"success": True, "completion": 100.0, "duration": 1.5,
                      "falls": 0, "collisions": 0}


def test_reaching_target_briefly_or_leaving_is_not_success():
    assert not score_run([frame(0), frame(1, 1), frame(1.4, 1)], [1, 0])["success"]
    result = score_run([frame(0), frame(1, 1), frame(2, 0.5)], [1, 0])
    assert not result["success"]
    assert result["completion"] == 100


def test_progress_uses_best_world_position_and_is_clamped():
    assert score_run([frame(0), frame(1, 0.5)], [1, 0])["completion"] == 50
    assert score_run([frame(0), frame(1, -2)], [1, 0])["completion"] == 0
    at_target = score_run([frame(0, 1), frame(0.5, 1)], [1, 0])
    assert at_target["success"] and at_target["completion"] == 100


def test_counts_event_edges_and_disqualifies_unsafe_run():
    frames = [frame(0, fallen=True, collisions=2),
              frame(0.2, fallen=True, collisions=3), frame(0.4),
              frame(0.6, 1, fallen=True, collisions=1), frame(1.1, 1)]
    result = score_run(frames, [1, 0])
    assert result["falls"] == 2
    assert result["collisions"] == 2
    assert not result["success"]


@pytest.mark.parametrize("change", [
    {"t": math.nan}, {"t": -1}, {"position": [0, 1]},
    {"position": [0, math.inf, 0]}, {"quaternion": [0, 0, 0, 0]},
    {"quaternion": [1, 0, 0]}, {"joints": [math.nan]},
    {"collisions": -1}, {"collisions": 1.2}, {"collisions": True},
    {"fallen": 1}, {"position": "abc"}, {"t": True},
])
def test_invalid_frames_are_rejected(change):
    with pytest.raises(ValueError):
        score_run([{**frame(0), **change}], [1, 0])


@pytest.mark.parametrize("frames", [[frame(1), frame(0)], [frame(0), frame(0)], [{}], [None]])
def test_invalid_timeline_or_missing_fields(frames):
    with pytest.raises(ValueError):
        score_run(frames, [1, 0])


@pytest.mark.parametrize("target,radius", [([1], 0.18), ([math.nan, 0], 0.18),
                                            ([1, 0], 0), ([1, 0], math.inf)])
def test_invalid_target_or_radius(target, radius):
    with pytest.raises(ValueError):
        score_run([], target, radius)


def test_single_frame_and_radius_boundary():
    assert not score_run([frame(0, 1)], [1, 0])["success"]
    assert score_run([frame(0, 0.82), frame(0.5, 0.82)], [1, 0])["success"]
