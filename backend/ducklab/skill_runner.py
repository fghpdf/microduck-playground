"""Execute official kick policies with a freely simulated ball, without pacing."""
from contextlib import redirect_stdout
import importlib.util
import sys
import threading
import time
from types import SimpleNamespace

CONTROL_DT = .02


def run_skill_scene(scene, rl, policies, emit):
    started = time.perf_counter()
    with redirect_stdout(sys.stderr):
        sys.path.insert(0, str(rl / 'src'))
        import mujoco
        import numpy as np
        import onnxruntime as ort
        from mjlab_microduck.sim.body_server import Body, World
        spec = importlib.util.spec_from_file_location('ducklab_kick_inference', rl / 'scripts/infer_policy.py')
        inference = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(inference)
        options = ort.SessionOptions()
        options.intra_op_num_threads = options.inter_op_num_threads = 1
        inference.ort = SimpleNamespace(InferenceSession=lambda path: ort.InferenceSession(
            path, sess_options=options, providers=['CPUExecutionProvider']))
        motor = inference.load_bam_model(inference.BAM_KP_FW, 7.4, None)
        xml = rl / 'src/mjlab_microduck/robot/microduck/scene_ball.xml'
        model, data, bam, _ = inference.load_mujoco_with_bam(str(xml), motor, .005, .1, inference.BAM_VIN_MIN)
        policy = inference.PolicyInference(model, data, walking_onnx_path=str(policies / 'alpha_walking.onnx'),
            standing_onnx_path=str(policies / 'alpha_stand.onnx'), action_scale=1., bam_ctrl=bam,
            use_projected_gravity=True, new_cmd_obs=True,
            kick_left_onnx_path=str(policies / 'ball_kick_left.onnx'),
            kick_right_onnx_path=str(policies / 'ball_kick_right.onnx'))
        adr = policy._trunk_qpos_adr
        data.qpos[adr:adr + 7] = [0, 0, .125, 1, 0, 0, 0]
        data.qpos[policy.joint_qpos_indices] = policy.default_pose
        bam.reset(data.qpos)
        policy.set_position_targets(policy.default_pose)
        mujoco.mj_forward(model, data)
        world = World.__new__(World)
        world.model, world.data, world.lock = model, data, threading.Lock()
        body = Body(world, 0)
        ball_geom = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, 'ball_geom')
        floor_geom = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, 'floor')

        def snapshot(contact=False):
            sensors = body.sensors()
            return dict(position=sensors['trunk'], quaternion=sensors['imu']['quat'],
                        joints=sensors['positions'], fallen=sensors['imu']['gravity'][2] > -.4,
                        collisions=0, objects=[dict(id='ball',kind='ball',radius=.035,position=data.qpos[policy.ball_qpos_adr:policy.ball_qpos_adr + 3].tolist())],
                        ball=data.qpos[policy.ball_qpos_adr:policy.ball_qpos_adr + 3].tolist(),
                        ball_contact=contact)

        def step():
            policy._update_policy_session()
            policy._update_command()
            policy.apply_action(policy.infer())
            contact = False
            for _ in range(4):
                bam.update()
                mujoco.mj_step(model, data)
                contact = contact or any(ball_geom in (int(c.geom1), int(c.geom2)) and
                    floor_geom not in (int(c.geom1), int(c.geom2)) for c in data.contact[:data.ncon])
            policy.update_behavior(CONTROL_DT)
            return snapshot(contact)

        for _ in range(50):
            initial = step()
        if initial['fallen'] or initial['position'][2] < .095:
            raise RuntimeError('kick standing warmup failed')
        # Set initial condition once before the recorded episode, then prevent
        # upstream keyboard trigger from teleporting the ball during the run.
        policy._place_ball(scene['skill'])
        mujoco.mj_forward(model, data)
        initial = snapshot()
        policy._place_ball = lambda behavior: None
    emit(dict(type='ready', target=scene['target'], start_pose=dict(position=initial['position'],
         quaternion=initial['quaternion']), objects=[dict(kind='ball', radius=.035, position=initial['ball'])],
         provenance=dict(controller='official-kick-policy', profile='offline-kick-bam-v1',
                         skill=scene['skill'], initial_condition='official-STAND2', action_scale=1.)))
    emit(dict(initial, type='frame', t=0))
    with redirect_stdout(sys.stderr):
        policy.trigger_behavior(scene['skill'])
    last = initial
    recovery_time = 0.0
    for index in range(round(scene['duration'] / CONTROL_DT)):
        with redirect_stdout(sys.stderr):
            last = step()
        emit(dict(last, type='frame', t=round((index + 1) * CONTROL_DT, 6)))
        # Keep the entire official kick and a short recovery, avoiding a long
        # ball-only tail after the robot has finished its action.
        if policy.behavior_mode is None:
            recovery_time += CONTROL_DT
        if recovery_time >= .4 or last['fallen']:
            break
    emit(dict(type='done', wall_seconds=time.perf_counter() - started, sim_seconds=round((index + 1) * CONTROL_DT, 6)))
