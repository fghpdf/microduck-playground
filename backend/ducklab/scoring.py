"""Score recorded world-space trajectories without trusting odometry."""

import math


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Expected a finite number")
    if not math.isfinite(value):
        raise ValueError("Expected a finite number")
    return float(value)


def _vector(value, size=None):
    if not isinstance(value, (list, tuple)) or (size is not None and len(value) != size):
        raise ValueError("Invalid vector")
    return tuple(_number(item) for item in value)


def _validate_frame(frame, previous_time):
    if not isinstance(frame, dict):
        raise ValueError("Invalid frame")
    try:
        time = _number(frame["t"])
        position = _vector(frame["position"], 3)
        quaternion = _vector(frame["quaternion"], 4)
        _vector(frame["joints"])
        collisions = frame["collisions"]
        fallen = frame["fallen"]
    except KeyError as error:
        raise ValueError("Missing frame field") from error
    if time < 0 or (previous_time is not None and time <= previous_time):
        raise ValueError("Frame timestamps must increase")
    if sum(component * component for component in quaternion) == 0:
        raise ValueError("Quaternion cannot be zero")
    if isinstance(collisions, bool) or not isinstance(collisions, int) or collisions < 0:
        raise ValueError("Collision count must be a nonnegative integer")
    if not isinstance(fallen, bool):
        raise ValueError("Fallen must be a boolean")
    return time, position, collisions > 0, fallen


def score_run(frames, target, radius=0.18):
    """Require a safe final half-second hold; report best distance progress."""
    target_xy = _vector(target, 2)
    radius = _number(radius)
    if radius <= 0 or not isinstance(frames, (list, tuple)):
        raise ValueError("Invalid radius or frame sequence")
    validated = []
    previous_time = None
    for frame in frames:
        current = _validate_frame(frame, previous_time)
        validated.append(current)
        previous_time = current[0]
    if not validated:
        return {"success": False, "completion": 0.0, "duration": 0.0,
                "falls": 0, "collisions": 0}
    distances = [math.hypot(position[0] - target_xy[0], position[1] - target_xy[1])
                 for _, position, _, _ in validated]
    falls = sum(fallen and (index == 0 or not validated[index - 1][3])
                for index, (_, _, _, fallen) in enumerate(validated))
    collisions = sum(contact and (index == 0 or not validated[index - 1][2])
                     for index, (_, _, contact, _) in enumerate(validated))
    final_hold_start = None
    for (time, _, _, _), distance in zip(validated, distances):
        if distance <= radius + 1e-12:
            if final_hold_start is None:
                final_hold_start = time
        else:
            final_hold_start = None
    held = final_hold_start is not None and validated[-1][0] - final_hold_start >= 0.5
    completion = (100.0 if distances[0] == 0 else
                  max(0.0, min(100.0, 100 * (1 - min(distances) / distances[0]))))
    return {"success": bool(held and not falls and not collisions),
            "completion": completion, "duration": validated[-1][0] - validated[0][0],
            "falls": falls, "collisions": collisions}
