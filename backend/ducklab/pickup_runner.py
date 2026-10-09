"""Official bow diagnostics and experimental contact-gripper pick and place.

The experimental model supplies jaw contact and compliant grasp forces absent
from the upstream robot XML. It is explicitly not validated hardware fidelity.
"""
import math

CONTROL_DT = .02


def pickup_evidence(objects, mouth_tip, initial_height):
    """Measure actual free-body lift and mouth distance; do not infer attachment."""
    if not objects:
        return {'lift_height': 0., 'mouth_distance': None, 'lifted': False,
                'grasp_supported': False}
    position = objects[0]['position']
    lift = max(0., position[2] - initial_height)
    distance = math.dist(position, mouth_tip) if mouth_tip is not None else None
    return {'lift_height': lift, 'mouth_distance': distance,
            'lifted': lift >= .025, 'grasp_supported': False}


def run_pickup_steps(step, trigger, duration, initial=None):
    """Execute upstream ground-pick motion, then settle; leave object physics alone."""
    trigger()
    initial_objects = (initial or {}).get('objects', [])
    initial_height = initial_objects[0]['position'][2] if initial_objects else 0.
    for index in range(int(round(duration / CONTROL_DT))):
        frame = step((0, 0))
        yield {**frame, 'type': 'frame', 't': round((index + 1) * CONTROL_DT, 6),
               'pickup': pickup_evidence(frame.get('objects', []), frame.get('mouth_tip'), initial_height)}
        if frame.get('fallen'):
            break


def add_trash(spec, scene):
    """Add a real freely moving lightweight box, without any grasp constraints."""
    import mujoco
    if scene.get('simulated_gripper'):
        site = next(site for site in spec.sites if site.name == 'mouth_tip')
        site.parent.add_geom(name='ducklab_simulated_gripper', type=mujoco.mjtGeom.mjGEOM_SPHERE,
                             pos=site.pos, size=[.018, 0, 0], mass=.0001,
                             contype=1, conaffinity=1, rgba=[1, .6, .1, .35])
    for obj in scene.get('objects', []):
        if obj.get('kind') != 'trash':
            continue
        position, size = obj['position'], obj['size']
        if (len(position) != 3 or len(size) != 3 or
                not all(math.isfinite(v) for v in [*position, *size]) or
                any(v <= 0 for v in size)):
            raise ValueError('invalid trash geometry')
        body = spec.worldbody.add_body(name='ducklab_trash', pos=position)
        body.add_freejoint(name='ducklab_trash_freejoint')
        body.add_geom(name='ducklab_trash_collision', type=mujoco.mjtGeom.mjGEOM_BOX,
                      size=[v / 2 for v in size], mass=.005, contype=1, conaffinity=1,
                      rgba=[.25, .6, .3, 1], friction=[.8, .005, .0001])


def object_snapshot(model, data):
    import mujoco
    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, 'ducklab_trash')
    if body_id < 0:
        return []
    geom_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, 'ducklab_trash_collision')
    contact = False
    for pair in data.contact[:data.ncon]:
        first, second = int(pair.geom1), int(pair.geom2)
        other = second if first == geom_id else first if second == geom_id else None
        if other is not None and model.geom_bodyid[other] not in (0, body_id):
            contact = True
    return [{'id': 'trash', 'kind': 'trash', 'position': data.xpos[body_id].tolist(),
             'quaternion': data.xquat[body_id].tolist(),
             'size': (2 * model.geom_size[geom_id]).tolist(), 'robot_contact': contact}]


class SimulatedContactGripper:
    """Experimental compliant grasp, gated by real mouth proximity and contact.

    Forces act on both the free object and robot; object qpos is never assigned.
    This augments the missing official jaw mechanics, not a hardware model.
    """
    def __init__(self, model, data):
        import mujoco
        self.model, self.data = model, data
        self.body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, 'ducklab_trash')
        self.site = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, 'mouth_tip')
        self.robot_body = int(model.site_bodyid[self.site])
        self.gripper_geom = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, 'ducklab_simulated_gripper')
        self.object_geom = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, 'ducklab_trash_collision')
        self.enabled = True
        self.attached = False
        self.released = False
        self.contact_seen = False

    def release(self):
        self.enabled, self.attached, self.released = False, False, True

    def update(self):
        import mujoco
        import numpy as np
        self.data.xfrc_applied[self.body] = 0
        self.data.xfrc_applied[self.robot_body] = 0
        tip = self.data.site_xpos[self.site]
        obj = self.data.xpos[self.body]
        contact = any({int(pair.geom1), int(pair.geom2)} == {self.gripper_geom, self.object_geom}
                      for pair in self.data.contact[:self.data.ncon])
        distance = float(np.linalg.norm(tip - obj))
        self.contact_seen = self.contact_seen or (contact and distance < .045)
        if self.enabled and not self.attached and contact and distance < .045:
            self.attached = True
        if not self.attached:
            return
        object_velocity = np.zeros(6)
        site_velocity = np.zeros(6)
        mujoco.mj_objectVelocity(self.model, self.data, mujoco.mjtObj.mjOBJ_BODY,
                                self.body, object_velocity, 0)
        mujoco.mj_objectVelocity(self.model, self.data, mujoco.mjtObj.mjOBJ_SITE,
                                self.site, site_velocity, 0)
        force = np.clip(20 * (tip - obj) + .2 * (site_velocity[3:] - object_velocity[3:]), -.8, .8)
        self.data.xfrc_applied[self.body, :3] = force
        self.data.xfrc_applied[self.robot_body, :3] = -force
        # Apply the equal/opposite pair at the object's COM to conserve total
        # linear and angular momentum across the two bodies.
        self.data.xfrc_applied[self.robot_body, 3:] = np.cross(self.data.xipos[self.body] - self.data.xipos[self.robot_body], -force)


def run_pick_place_steps(step, trigger, release, target, duration, initial):
    """Bow, carry using official walking, lower, release and physically settle."""
    trigger()
    previous = initial
    phase = 'pick'
    phase_since = 0.
    baseline = initial['objects'][0]['position'][2]
    for index in range(int(round(duration / CONTROL_DT))):
        t = (index + 1) * CONTROL_DT
        command = (0, 0)
        if phase == 'transport':
            # Position the mouth (forward of trunk), rather than trunk, at B.
            item = previous['objects'][0]['position']
            # The bow lowers the mouth behind its standing location. Approach
            # a modest forward pre-place waypoint, then release near B.
            placement_waypoint = [target[0] + .055, target[1]]
            offset = [item[0] - previous['position'][0], item[1] - previous['position'][1]]
            root_target = [placement_waypoint[0] - offset[0], placement_waypoint[1] - offset[1]]
            heading = math.atan2(root_target[1] - previous['position'][1], root_target[0] - previous['position'][0])
            from .fast_runner import yaw
            error = math.atan2(math.sin(heading - yaw(previous['quaternion'])), math.cos(heading - yaw(previous['quaternion'])))
            command = (.3, max(-.5, min(.5, 2 * error)))
            if math.dist(item[:2], placement_waypoint) < .035:
                phase, phase_since = 'place', t
                command = (0, 0)
                trigger()
        frame = step(command)
        frame = {**frame, 'objects': [{**obj, 'attached': frame.get('gripper', {}).get('attached', False)} for obj in frame.get('objects', [])]}
        if phase == 'pick' and t >= 3.1:
            phase, phase_since = 'transport', t
        if phase == 'place' and t - phase_since > .65 and frame['mouth_tip'][2] < .065:
            release()
            phase, phase_since = 'settle', t
        evidence = pickup_evidence(frame.get('objects', []), frame.get('mouth_tip'), baseline)
        yield {**frame, 'type': 'frame', 't': round(t, 6),
               'pickup': {**evidence, **frame.get('gripper', {}), 'phase': phase,
                          'grasp_supported': True, 'grasp_model': 'simulated-contact-gripper-v1'}}
        previous = frame
        if frame.get('fallen') or (phase == 'settle' and t - phase_since >= 3.):
            break
