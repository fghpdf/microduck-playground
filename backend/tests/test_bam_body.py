from pathlib import Path

import numpy as np
import pytest

from ducklab.bam_body import create_body

RL = Path(__file__).resolve().parents[3] / 'vendor/microduck_rl'


@pytest.fixture
def pair():
    return create_body(RL)


def test_targets_follow_protocol_names_and_do_not_write_motor_torque(pair):
    world, body = pair
    before = world.data.ctrl.copy()
    targets = [index * .01 for index in range(15)]
    body.set_targets(targets)
    from mjlab_microduck.sim.body_server import JOINT_NAMES
    for name, target in zip(world.actuator_names, world.bam_ctrl.q_target):
        assert target == targets[JOINT_NAMES.index(name)]
    np.testing.assert_array_equal(world.data.ctrl, before)
    with pytest.raises(ValueError):
        body.set_targets([0])


def test_torque_and_gain_change_bam_firmware_without_position_bias(pair):
    world, body = pair
    gain = world.model.actuator_gainprm.copy()
    bias = world.model.actuator_biasprm.copy()
    body.set_gain(123)
    assert world.bam_ctrl.model.actuator.kp == 123
    body.set_torque(False)
    assert world.bam_ctrl.model.actuator.kp == 0
    body.set_torque(True)
    assert world.bam_ctrl.model.actuator.kp == 123 and body.released
    np.testing.assert_array_equal(world.bam_ctrl.q_target, world.data.qpos[world.bam_ctrl.qpos_indexes])
    np.testing.assert_array_equal(world.model.actuator_gainprm, gain)
    np.testing.assert_array_equal(world.model.actuator_biasprm, bias)


def test_every_physics_step_updates_bam_first_and_holds_until_enabled(pair, monkeypatch):
    import mujoco
    world, body = pair
    order = []
    monkeypatch.setattr(world.bam_ctrl, 'update', lambda: order.append('bam'))
    monkeypatch.setattr(mujoco, 'mj_step', lambda *args: order.append('physics'))
    monkeypatch.setattr(body, 'restore', lambda: order.append('hold'))
    world.step(2)
    assert order == ['bam', 'physics', 'hold'] * 2
    order.clear()
    body.set_torque(True)
    world.step()
    assert order == ['bam', 'physics']


def test_placement_initializes_bam_targets_and_preserves_sensors(pair):
    world, body = pair
    np.testing.assert_array_equal(world.bam_ctrl.q_target, world.data.qpos[world.bam_ctrl.qpos_indexes])
    assert not body.released
    sensors = body.sensors()
    assert len(sensors['positions']) == 15 and sensors['sim_time'] == 0
    assert world.model.opt.timestep == .005


def test_torque_off_removes_active_motor_braking_before_physics(pair, monkeypatch):
    import mujoco
    world, body = pair
    body.set_torque(False)
    def update():
        world.data.ctrl[body.actuator_slice] = 1.0  # Motor back-EMF can persist even at kp=0.
    def physics(*args):
        np.testing.assert_array_equal(world.data.ctrl[body.actuator_slice], 0)
    monkeypatch.setattr(world.bam_ctrl, 'update', update)
    monkeypatch.setattr(mujoco, 'mj_step', physics)
    world.step()
