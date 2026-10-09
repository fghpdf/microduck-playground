"""Task scores from physical object trajectories and observed contacts."""
import math
from .scoring import _number, _vector, _validate_frame, score_run


def score_scene(frames, scene, target=None):
    if scene.get('task_type') == 'pickup':
        from .pickup_scoring import score_pickup
        return score_pickup(frames, scene)
    if scene.get('task_type') != 'football':
        return score_run(frames, target or scene['target'])
    goal = scene['goal']
    goal_x, goal_y, width = (_number(goal[key]) for key in ('x', 'y', 'width'))
    if width <= 0:
        raise ValueError('Goal width must be positive')
    previous_time = None
    previous_ball = None
    contact_seen = False
    crossed = False
    falls = collisions = 0
    prior_fall = prior_collision = False
    balls = []
    times = []
    for frame in frames:
        time, _, collision, fallen = _validate_frame(frame, previous_time)
        ball = _vector(frame['ball'], 3)
        contact = frame['ball_contact']
        if not isinstance(contact, bool):
            raise ValueError('Ball contact must be a boolean')
        contact_seen = contact_seen or contact
        if previous_ball and previous_ball[0] < goal_x <= ball[0]:
            fraction = (goal_x - previous_ball[0]) / (ball[0] - previous_ball[0])
            crossing_y = previous_ball[1] + fraction * (ball[1] - previous_ball[1])
            crossed = crossed or (contact_seen and abs(crossing_y - goal_y) <= width / 2)
        falls += fallen and not prior_fall
        collisions += collision and not prior_collision
        previous_time, previous_ball = time, ball
        prior_fall, prior_collision = fallen, collision
        balls.append(ball)
        times.append(time)
    travel = max((math.dist(balls[0], ball) for ball in balls), default=0)
    remaining = goal_x - balls[0][0] if balls else 0
    progress = max((ball[0] - balls[0][0] for ball in balls), default=0)
    completion = min(100., max(0., 100 * progress / remaining)) if remaining > 0 else 0.
    return dict(success=bool(crossed and not falls and not collisions), completion=completion,
                duration=times[-1] - times[0] if times else 0., falls=int(falls), collisions=int(collisions),
                goal_crossed=crossed, ball_contact=contact_seen, ball_travel=travel,
                details=dict(goal_crossed=crossed, ball_contact=contact_seen, ball_distance=travel))
