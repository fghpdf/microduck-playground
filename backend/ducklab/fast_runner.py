"""Offline reference navigation: fixed simulation steps, no wall-clock pacing.

This runs upstream CPU PolicyInference from its official STAND2 initial pose;
it is deliberately separate from the interactive robotd/CLI control profile.
"""
import argparse
from contextlib import redirect_stdout
import importlib.util
import json
import math
from pathlib import Path
import sys
import time

from .scenarios import get_scenario

CONTROL_DT = .02


def yaw(quaternion):
    w, x, y, z = quaternion
    return math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))


def world_target(position, quaternion, relative_target):
    heading = yaw(quaternion)
    x, y = relative_target
    return [position[0] + math.cos(heading) * x - math.sin(heading) * y,
            position[1] + math.sin(heading) * x + math.cos(heading) * y]


def navigate(position, quaternion, target):
    dx, dy = target[0] - position[0], target[1] - position[1]
    if math.hypot(dx, dy) < .12:
        return (0, 0)
    error = math.atan2(dy, dx) - yaw(quaternion)
    error = math.atan2(math.sin(error), math.cos(error))
    return (.3, max(-.5, min(.5, 2 * error)))


def run_steps(step, target, duration, initial=None, waypoints=None):
    previous = initial or {'position': [0, 0], 'quaternion': [1, 0, 0, 0]}
    route = [*list(waypoints or []), target]
    waypoint_index = 0
    settling = 0
    stopping = False
    for index in range(int(round(duration / CONTROL_DT))):
        while waypoint_index < len(route) - 1 and math.dist(previous['position'][:2], route[waypoint_index]) < .18:
            waypoint_index += 1
        command = (0, 0) if stopping else navigate(previous['position'], previous['quaternion'], route[waypoint_index])
        stopping = stopping or command == (0, 0)
        frame = step(command)
        frame = {**frame, 'type': 'frame', 't': round((index + 1) * CONTROL_DT, 6)}
        yield frame
        previous = frame
        distance = math.hypot(target[0] - frame['position'][0], target[1] - frame['position'][1])
        settling = settling + 1 if command == (0, 0) and distance < .18 else 0
        if frame['fallen'] or settling >= 30:
            break


def create_stepper(rl, policies, scene=None):
    sys.path.insert(0, str(rl / 'src'))
    import mujoco
    import numpy as np
    from mjlab_microduck.sim.body_server import Body, World, DEFAULT_SCENE
    spec = importlib.util.spec_from_file_location('ducklab_offline_inference', rl / 'scripts/infer_policy.py')
    inference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(inference)
    # Bound CPU inference threads for predictable local batch execution.
    from types import SimpleNamespace
    import onnxruntime as ort
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    inference.ort = SimpleNamespace(InferenceSession=lambda path: ort.InferenceSession(
        path, sess_options=options, providers=['CPUExecutionProvider']))
    motor = inference.load_bam_model(inference.BAM_KP_FW, 7.4, None)
    from .scene_geometry import load_scene_with_bam
    model, data, bam, _ = load_scene_with_bam(inference, DEFAULT_SCENE, motor, .005, scene)
    policy = inference.PolicyInference(model, data, walking_onnx_path=str(policies / 'alpha_walking.onnx'),
                                       standing_onnx_path=str(policies / 'alpha_stand.onnx'),
                                       action_scale=1.0, bam_ctrl=bam, use_projected_gravity=True,
                                       new_cmd_obs=True, ground_pick_onnx_path=str(policies / 'alpha_ground_pick.onnx') if (scene or {}).get('skill') == 'ground_pick' else None)
    adr = int(model.jnt_qposadr[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, 'trunk_base_freejoint')])
    data.qpos[adr:adr + 7] = [0, 0, .125, 1, 0, 0, 0]
    data.qpos[policy.joint_qpos_indices] = policy.default_pose
    bam.reset(data.qpos)
    policy.set_position_targets(policy.default_pose)
    mujoco.mj_forward(model, data)
    world = World.__new__(World)
    import threading
    world.model, world.data, world.lock = model, data, threading.Lock()
    body = Body(world, 0)
    obstacle_geoms = {i for i in range(model.ngeom)
                      if model.geom_bodyid[i] == 0 and model.geom_type[i] != mujoco.mjtGeom.mjGEOM_PLANE and not (mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, i) or '').startswith('ducklab_terrain_')}

    from .pickup_runner import SimulatedContactGripper
    gripper = SimulatedContactGripper(model, data) if (scene or {}).get('simulated_gripper') else None

    def step(command):
        policy.vel_cmd = np.array([command[0], 0, command[1]], dtype=np.float32)
        policy._update_policy_session()
        policy._update_command()
        policy.update_ground_pick_phase(CONTROL_DT)
        policy.apply_action(policy.infer())
        collisions = 0
        for _ in range(4):
            if gripper is not None:
                gripper.update()
            bam.update()
            mujoco.mj_step(model, data)
            contacts = sum(1 for contact in data.contact[:data.ncon]
                           if int(contact.geom1) in obstacle_geoms or int(contact.geom2) in obstacle_geoms)
            collisions = max(collisions, contacts)
        sensors = body.sensors()
        from .pickup_runner import object_snapshot
        mouth_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, 'mouth_tip')
        extra = {'objects': object_snapshot(model, data), 'mouth_tip': data.site_xpos[mouth_id].tolist()} if (scene or {}).get('skill') == 'ground_pick' else {}
        if gripper is not None:
            extra = {**extra, 'gripper': {'attached': gripper.attached, 'released': gripper.released, 'contact_seen': gripper.contact_seen}}
        return {**extra, 'position': sensors['trunk'], 'quaternion': sensors['imu']['quat'],
                'joints': sensors['positions'], 'fallen': sensors['imu']['gravity'][2] > -.4,
                'collisions': collisions}
    step.trigger_ground_pick = policy.trigger_ground_pick
    step.release_gripper = gripper.release if gripper is not None else lambda: None
    return step


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rl', type=Path, required=True)
    parser.add_argument('--policies', type=Path, required=True)
    parser.add_argument('--scenario', required=True)
    args = parser.parse_args()
    scene = get_scenario(args.scenario)
    if scene is None:
        parser.error('unknown scenario')
    if scene.get('task_type') == 'football':
        from .skill_runner import run_skill_scene
        run_skill_scene(scene, args.rl, args.policies,
                        lambda row: print(json.dumps(row, allow_nan=False), flush=True))
        return
    started = time.perf_counter()
    with redirect_stdout(sys.stderr):
        step = create_stepper(args.rl, args.policies, scene)
        for _ in range(50):
            initial = step((0, 0))
    if initial['fallen'] or initial['position'][2] < .095:
        raise RuntimeError('offline standing warmup failed')
    target = scene['target'] if scene.get('target_frame') == 'world' else world_target(
        initial['position'], initial['quaternion'], scene['target'])
    def emit(value):
        print(json.dumps(value, allow_nan=False), flush=True)
    emit({'type': 'ready', 'target': target,
          'start_pose': {'position': initial['position'], 'quaternion': initial['quaternion']},
          'provenance': {'controller': 'official-ground-pick-policy' if scene.get('task_type') in ('pickup', 'pick_place') else 'reference-navigation', 'profile': 'offline-ground-pick-bam-v1' if scene.get('task_type') in ('pickup', 'pick_place') else 'offline-alpha-bam-v1',
                         'initial_condition': 'official-STAND2', 'action_scale': 1.0, **({'grasp_model': 'simulated-contact-gripper-v1', 'experimental': True} if scene.get('simulated_gripper') else {})}})
    emit({**initial, 'type': 'frame', 't': 0})
    def quiet_step(command):
        with redirect_stdout(sys.stderr):
            return step(command)
    last = initial
    if scene.get('simulated_gripper'):
        from .pickup_runner import run_pick_place_steps
        def trigger():
            with redirect_stdout(sys.stderr):
                step.trigger_ground_pick()
        rows = run_pick_place_steps(quiet_step, trigger, step.release_gripper, target, scene['duration'], initial)
    elif scene.get('skill') == 'ground_pick':
        from .pickup_runner import run_pickup_steps
        with redirect_stdout(sys.stderr):
            step.trigger_ground_pick()
        rows = run_pickup_steps(quiet_step, lambda: None, scene['duration'], initial)
    else:
        rows = run_steps(quiet_step, target, scene['duration'], initial=initial, waypoints=scene.get('waypoints'))
    for last in rows:
        emit(last)
    emit({'type': 'done', 'wall_seconds': time.perf_counter() - started,
          'sim_seconds': last['t']})


if __name__ == '__main__':
    main()
