"""Official body protocol backed by the policy training's BAM M6 actuators."""
import importlib.util
import sys
import threading


def create_body(rl, scene=None):
    """Reuse upstream CPU BAM loaders without importing the torch training stack."""
    sys.path.insert(0, str(rl / "src"))
    import mujoco
    from mjlab_microduck.sim import body_server as official
    spec = importlib.util.spec_from_file_location("ducklab_official_inference", rl / "scripts/infer_policy.py")
    inference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(inference)

    class BamWorld(official.World):
        def __init__(self):
            motor = inference.load_bam_model(inference.BAM_KP_FW, 7.4, None)
            from .scene_geometry import load_scene_with_bam
            self.model, self.data, self.bam_ctrl, self.actuator_names = load_scene_with_bam(
                inference, official.DEFAULT_SCENE, motor, official.TIMESTEP, scene)
            self.lock = threading.Lock()
            self.bodies = []
            self.obstacle_geoms = {i for i in range(self.model.ngeom)
                                   if self.model.geom_bodyid[i] == 0 and
                                   self.model.geom_type[i] != mujoco.mjtGeom.mjGEOM_PLANE and not (mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_GEOM, i) or '').startswith('ducklab_terrain_')}
            self.last_collisions = 0

        def step(self, times=1):
            with self.lock:
                self.last_collisions = 0
                for _ in range(times):
                    self.bam_ctrl.update()
                    for body in self.bodies:
                        if not body.torque_on:
                            self.data.ctrl[body.actuator_slice] = 0.0
                    mujoco.mj_step(self.model, self.data)
                    contacts = sum(1 for contact in self.data.contact[:self.data.ncon]
                                   if int(contact.geom1) in self.obstacle_geoms or
                                   int(contact.geom2) in self.obstacle_geoms)
                    self.last_collisions = max(self.last_collisions, contacts)
                    for body in self.bodies:
                        if not body.released:
                            body.restore()

    class BamBody(official.Body):
        def _apply_torque(self):
            self.world.bam_ctrl.model.actuator.kp = self.kp if self.torque_on else 0.0

        def place(self, pose, trunk_z, offset_y):
            super().place(pose, trunk_z, offset_y)
            self.world.bam_ctrl.reset(self.world.data.qpos)
            # The inherited placement writes angles to ctrl; BAM motors need torques.
            self.world.data.ctrl[self.actuator_slice] = 0.0

        def set_targets(self, wire_targets):
            if len(wire_targets) != len(official.JOINT_NAMES):
                raise ValueError(f"expected {len(official.JOINT_NAMES)} targets, got {len(wire_targets)}")
            with self.world.lock:
                self.world.bam_ctrl.q_target = self.world.bam_ctrl.q_target.copy()
                for name in self.world.actuator_names:
                    self.world.bam_ctrl.set_q_target(name, wire_targets[official.JOINT_NAMES.index(name)])

        def set_torque(self, on):
            with self.world.lock:
                self.torque_on = bool(on)
                if on:
                    self.released = True
                    self.world.bam_ctrl.reset(self.world.data.qpos)
                self._apply_torque()

    world = BamWorld()
    body = BamBody(world, 0)
    pose, height = official.pose_table(official.DEFAULT_SCENE, "SIT")
    body.place(pose, height, 0.0)
    world.bodies.append(body)
    mujoco.mj_forward(world.model, world.data)
    return world, body
