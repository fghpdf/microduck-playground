"""Scene boxes and BAM scene loading; dimensions are full lengths in metres."""
import math


def add_obstacles(spec, scene):
    import mujoco
    for index, box in enumerate((scene or {}).get('obstacles', [])):
        position, size, yaw = box['position'], box['size'], box.get('yaw', 0)
        if (len(position) != 3 or len(size) != 3 or
                not all(math.isfinite(value) for value in [*position, *size, yaw]) or
                any(value <= 0 for value in size)):
            raise ValueError('invalid obstacle box')
        spec.worldbody.add_geom(name=f'ducklab_obstacle_{index}', type=mujoco.mjtGeom.mjGEOM_BOX,
                                pos=position, size=[value / 2 for value in size],
                                quat=[math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)],
                                contype=1, conaffinity=1, rgba=[.9, .45, .15, 1])

    for index, ramp in enumerate((scene or {}).get('terrain', [])):
        position, size = ramp['position'], ramp['size']
        direction = ramp.get('direction', 1)
        if (ramp.get('kind') != 'ramp' or direction not in (-1, 1) or
                len(position) != 3 or len(size) != 3 or
                not all(math.isfinite(value) for value in [*position, *size]) or
                any(value <= 0 for value in size)):
            raise ValueError('invalid ramp terrain')
        half_length, half_width, height = size[0] / 2, size[1] / 2, size[2]
        low, high = -direction * half_length, direction * half_length
        vertices = [[low, -half_width, 0], [low, half_width, 0],
                    [high, -half_width, 0], [high, half_width, 0],
                    [high, -half_width, height], [high, half_width, height]]
        mesh_name = f'ducklab_ramp_mesh_{index}'
        spec.add_mesh(name=mesh_name, uservert=[v for vertex in vertices for v in vertex])
        spec.worldbody.add_geom(name=f'ducklab_terrain_{index}', type=mujoco.mjtGeom.mjGEOM_MESH,
                                meshname=mesh_name, pos=position, contype=1, conaffinity=1,
                                rgba=[.32, .58, .7, 1], friction=[1, .005, .0001])


def load_scene_with_bam(inference, xml_path, motor, timestep, scene=None):
    """Adapt upstream load_mujoco_with_bam, inserting geometry before compilation."""
    if not (scene or {}).get('obstacles') and not (scene or {}).get('terrain') and not (scene or {}).get('objects'):
        return inference.load_mujoco_with_bam(str(xml_path), motor, timestep, .1, inference.BAM_VIN_MIN)
    import mujoco
    import numpy as np
    from bam.mujoco import MujocoController
    force_limit = motor.actuator.vin * motor.kt.value / motor.R.value
    spec = mujoco.MjSpec.from_file(str(xml_path))
    add_obstacles(spec, scene)
    from .pickup_runner import add_trash
    add_trash(spec, scene or {})
    names = []
    for act in spec.actuators:
        target = act.target
        target_name = target.name if hasattr(target, 'name') else str(target)
        if target_name.startswith('passive_'):
            continue
        act.set_to_motor()
        act.forcelimited, act.forcerange = True, (-force_limit, force_limit)
        act.ctrllimited, act.gear = False, [1., 0, 0, 0, 0, 0]
        names.append(act.name)
        for joint in spec.joints:
            if joint.name == target_name:
                joint.damping, joint.frictionloss = np.zeros((3, 1)), 0.
                joint.solref_friction = inference.BAM_STIFF_SOLREF_FRICTION
                joint.solimp_friction = inference.BAM_STIFF_SOLIMP_FRICTION
                break
    model = spec.compile()
    model.opt.timestep = timestep
    data = mujoco.MjData(model)
    controller = MujocoController(motor, names, model, data, vin_drop_gain=.1,
                                 vin_min=inference.BAM_VIN_MIN)
    return model, data, controller, names
