from ducklab.pickup_runner import pickup_evidence, run_pickup_steps


def test_bowing_near_object_is_not_lift():
    result = pickup_evidence([{'position': [.1, 0, .01]}], [.1, 0, .01], .01)
    assert result['mouth_distance'] == 0
    assert result['lifted'] is False
    assert result['grasp_supported'] is False


def test_actual_height_change_reports_lift():
    result = pickup_evidence([{'position': [.1, 0, .05]}], [.1, 0, .05], .01)
    assert result['lifted'] is True
    assert result['lift_height'] == .04
    assert result['grasp_supported'] is False


def test_missing_object_does_not_claim_lift():
    assert pickup_evidence([], None, .01)['lifted'] is False


def test_ground_pick_trigger_and_frames_preserve_physical_positions():
    calls = []
    frame = {'objects': [{'position': [.1, 0, .01]}], 'mouth_tip': [.1, 0, .01], 'fallen': False}
    rows = list(run_pickup_steps(lambda command: frame, lambda: calls.append('trigger'), .04, frame))
    assert calls == ['trigger']
    assert len(rows) == 2
    assert rows[-1]['t'] == .04
    assert rows[-1]['objects'] == frame['objects']
    assert rows[-1]['pickup']['lifted'] is False


def test_fall_ends_exercise():
    rows = list(run_pickup_steps(lambda command: {'fallen': True}, lambda: None, 4))
    assert len(rows) == 1


def test_trash_is_free_body_with_real_collision_and_finite_size():
    import mujoco
    import pytest
    from ducklab.pickup_runner import add_trash, object_snapshot
    scene = {'objects': [{'kind': 'trash', 'position': [.1, 0, .01], 'size': [.02, .025, .02]}]}
    spec = mujoco.MjSpec()
    add_trash(spec, scene)
    model = spec.compile()
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    assert model.nq == 7
    assert model.neq == 0
    assert model.geom_contype[0] == 1
    assert object_snapshot(model, data)[0]['position'] == [.1, 0, .01]
    snapshot = object_snapshot(model, data)[0]
    assert snapshot['size'] == [.02, .025, .02]
    assert snapshot['quaternion'] == [1., 0., 0., 0.]
    data.qpos[3:7] = [.7071067811865476, 0., 0., .7071067811865476]
    mujoco.mj_forward(model, data)
    assert object_snapshot(model, data)[0]['quaternion'] == pytest.approx(data.qpos[3:7])
    assert not snapshot['robot_contact']
    with pytest.raises(ValueError):
        add_trash(mujoco.MjSpec(), {'objects': [{'kind': 'trash', 'position': [0, 0, 0], 'size': [-1, 1, 1]}]})


def test_simulated_gripper_requires_its_contact_and_releases_forces():
    import mujoco
    import numpy as np
    from ducklab.pickup_runner import SimulatedContactGripper
    model = mujoco.MjModel.from_xml_string('''<mujoco><worldbody>
      <body name="head" pos="0 0 .2"><freejoint/>
        <geom name="ducklab_simulated_gripper" type="sphere" size=".018" mass=".1"/>
        <site name="mouth_tip"/>
      </body>
      <body name="ducklab_trash" pos=".1 0 .2"><freejoint/>
        <geom name="ducklab_trash_collision" type="box" size=".01 .0125 .01" mass=".005"/>
      </body></worldbody></mujoco>''')
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    gripper = SimulatedContactGripper(model, data)
    gripper.update()
    assert not gripper.attached
    assert not np.any(data.xfrc_applied)
    data.qpos[7] = .025
    mujoco.mj_forward(model, data)
    assert data.ncon > 0
    gripper.update()
    assert gripper.attached and gripper.contact_seen
    assert np.allclose(data.xfrc_applied[gripper.body, :3] +
                       data.xfrc_applied[gripper.robot_body, :3], 0)
    total_torque = sum((np.cross(data.xipos[body], data.xfrc_applied[body, :3]) +
                        data.xfrc_applied[body, 3:] for body in (gripper.body, gripper.robot_body)))
    assert np.allclose(total_torque, 0)
    gripper.release()
    gripper.update()
    assert gripper.released and not gripper.attached
    assert not np.any(data.xfrc_applied)
