"""Require an observed lift, carry, release and stable landing at B."""
import math
from .scoring import _validate_frame, _vector


def _object_state(frame):
    item = next((obj for obj in frame.get('objects', []) if obj.get('id') == 'trash'), None)
    if item is None:
        return None
    position = _vector(item['position'], 3)
    contact, attached = item.get('robot_contact', False), item.get('attached', False)
    if not isinstance(contact, bool) or not isinstance(attached, bool):
        raise ValueError('object contact and attachment must be boolean')
    return position, contact, attached


def score_pickup(frames, scene):
    previous = baseline = held_since = landed_since = landed_position = None
    peak = 0.
    picked_up = transported = placed = contact_seen = False
    falls = collisions = 0
    previous_fall = previous_collision = False
    times = []
    target = _vector(scene.get('target', [.6, 0]), 2)
    for frame in frames:
        t, _, collision, fallen = _validate_frame(frame, previous)
        previous = t
        times.append(t)
        falls += bool(fallen and not previous_fall)
        collisions += bool(collision and not previous_collision)
        previous_fall, previous_collision = fallen, collision
        state = _object_state(frame)
        if state is None:
            held_since = landed_since = landed_position = None
            placed = False
            continue
        position, contact, attached = state
        baseline = position[2] if baseline is None else baseline
        lift = max(0., position[2] - baseline)
        peak = max(peak, lift)
        contact_seen = contact_seen or contact
        held = contact or attached
        if lift >= .025 and held:
            held_since = t if held_since is None else held_since
            picked_up = picked_up or t - held_since >= .5
        else:
            held_since = None
        near_target = math.hypot(position[0] - target[0], position[1] - target[1]) <= .12
        transported = transported or (picked_up and held and lift >= .025 and near_target)
        landing = transported and not held and near_target and position[2] <= baseline + .015
        if landing:
            if landed_position is None or math.dist(position, landed_position) > .015:
                landed_since, landed_position = t, position
            placed = t - landed_since >= .5
        else:
            landed_since = landed_position = None
            placed = False
    duration = times[-1] - times[0] if times else 0.
    supported = (scene.get('simulated_gripper') is True and
                 scene.get('grasp_model') == 'simulated-contact-gripper-v1')
    return {'success': bool(placed and not falls and not collisions),
            'completion': 100. if placed else 66. if transported else 33. if picked_up else 0.,
            'duration': duration, 'falls': falls, 'collisions': collisions,
            'details': {'action_completed': bool(placed),
                        'peak_lift': peak, 'object_contact': contact_seen,
                        'sustained_lift': picked_up, 'picked_up': picked_up,
                        'transported': transported, 'placed': placed,
                        'grasp_supported': supported,
                        'grasp_model': scene.get('grasp_model') if supported else None}}
