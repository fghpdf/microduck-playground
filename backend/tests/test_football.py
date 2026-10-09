import pytest
from ducklab.skill_scoring import score_scene


def frame(t, x, y=0, contact=False, fallen=False):
    return dict(t=t, position=[0, 0, .12], quaternion=[1, 0, 0, 0], joints=[],
                collisions=0, fallen=fallen, ball=[x, y, .035], ball_contact=contact)


SCENE = dict(task_type='football', goal=dict(x=.4, y=0, width=1.0), target=[.4, 0])


def test_goal_requires_real_contact_and_crossing():
    assert score_scene([frame(0, .08), frame(.02, .09, contact=True), frame(1, .45)], SCENE)['success']
    assert not score_scene([frame(0, .08), frame(1, .45)], SCENE)['success']
    assert not score_scene([frame(0, .08), frame(.02, .09, contact=True), frame(1, .45, y=.7)], SCENE)['success']


def test_fall_invalidates_goal_and_stationary_ball_does_not_score():
    assert not score_scene([frame(0, .08), frame(1, .08, contact=True)], SCENE)['success']
    assert not score_scene([frame(0, .08), frame(.02, .09, contact=True), frame(1, .45, fallen=True)], SCENE)['success']


def test_ball_coordinates_validated():
    with pytest.raises(ValueError):
        score_scene([frame(0, float('nan'))], SCENE)


def test_crossing_interpolates_ball_path_not_final_position():
    result = score_scene([frame(0, .08, contact=True), frame(1, .6, y=.55)], SCENE)
    assert result['success']
    assert result['ball_travel'] > .5


def test_late_contact_does_not_retroactively_count_crossing():
    assert not score_scene([frame(0, .08), frame(1, .6), frame(2, .7, contact=True)], SCENE)['success']


def test_invalid_contact_and_goal_width_rejected():
    with pytest.raises(ValueError):
        score_scene([frame(0, .08, contact=1)], SCENE)
    with pytest.raises(ValueError):
        score_scene([], {**SCENE, 'goal': dict(x=.4, y=0, width=0)})


def test_empty_episode_is_unsuccessful():
    assert score_scene([], SCENE)['success'] is False


def test_catalog_has_both_official_kick_tasks():
    from ducklab.scenarios import get_scenario
    for side in ('left', 'right'):
        scene = get_scenario('football_' + side)
        assert scene['skill'] == 'kick_' + side
        assert scene['fast_only']
        assert scene['category'] == 'football'
