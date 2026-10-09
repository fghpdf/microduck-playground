import pytest
from ducklab.pickup_scoring import score_pickup

SCENE = {'duration': 30, 'target': [.6, 0], 'simulated_gripper': True,
         'grasp_model': 'simulated-contact-gripper-v1'}


def frame(t, z=.01, contact=False, x=.1, attached=False):
    return {'t': t, 'position': [0, 0, .12], 'quaternion': [1, 0, 0, 0],
            'joints': [], 'fallen': False, 'collisions': 0,
            'objects': [{'id': 'trash', 'position': [x, 0, z],
                         'robot_contact': contact, 'attached': attached}]}


def test_bow_completion_is_not_transport():
    result = score_pickup([frame(0), frame(15), frame(30)], SCENE)
    assert not result['success']
    assert not result['details']['action_completed']
    assert result['completion'] == 0


def test_lift_and_carry_without_release_is_not_success():
    rows = [frame(0), frame(1, .05, True), frame(1.6, .05, True),
            frame(6, .05, True, .6)]
    result = score_pickup(rows, SCENE)
    assert not result['success']
    assert result['details']['picked_up']
    assert result['details']['transported']
    assert not result['details']['placed']


def test_real_pick_carry_release_and_settle_succeeds():
    rows = [frame(0), frame(1, .05, True, attached=True),
            frame(1.6, .05, attached=True), frame(6, .05, x=.6, attached=True),
            frame(7, x=.6), frame(7.6, x=.6)]
    result = score_pickup(rows, SCENE)
    assert result['success'] and result['completion'] == 100
    assert result['details']['placed']
    assert result['details']['action_completed']
    assert result['duration'] < SCENE['duration']
    assert result['details']['grasp_supported']


def test_teleport_to_destination_without_pickup_fails():
    assert not score_pickup([frame(0), frame(1, x=.6), frame(2, x=.6)], SCENE)['success']


def test_airborne_or_unstable_release_does_not_place():
    prefix = [frame(0), frame(1, .05, True), frame(1.6, .05, True), frame(6, .05, True, .6)]
    assert not score_pickup(prefix + [frame(7, .05, x=.6), frame(8, .05, x=.6)], SCENE)['success']
    assert not score_pickup(prefix + [frame(7, x=.55), frame(7.6, x=.65)], SCENE)['success']


def test_missing_objects_and_empty_frames_fail():
    assert not score_pickup([], SCENE)['success']
    row = frame(0)
    row.pop('objects')
    assert not score_pickup([row], SCENE)['success']


def test_nonfinite_object_rejected():
    with pytest.raises(ValueError):
        score_pickup([frame(0, float('nan'))], SCENE)


def test_success_is_revoked_if_object_moves_after_landing():
    rows = [frame(0), frame(1, .05, True), frame(1.6, .05, True),
            frame(6, .05, True, .6), frame(7, x=.6), frame(7.6, x=.6), frame(8, x=.9)]
    assert not score_pickup(rows, SCENE)['success']


def test_simulated_grasp_provenance_is_explicit():
    assert not score_pickup([], {'target': [.6, 0]})['details']['grasp_supported']
    assert score_pickup([], SCENE)['details']['grasp_supported']


def test_invalid_attachment_rejected():
    row = frame(0)
    row['objects'][0]['attached'] = 'yes'
    with pytest.raises(ValueError):
        score_pickup([row], SCENE)


def test_missing_final_object_revokes_success():
    rows = [frame(0), frame(1, .05, True), frame(1.6, .05, True),
            frame(6, .05, True, .6), frame(7, x=.6), frame(7.6, x=.6)]
    final = frame(8)
    final.pop('objects')
    assert not score_pickup(rows + [final], SCENE)['success']
