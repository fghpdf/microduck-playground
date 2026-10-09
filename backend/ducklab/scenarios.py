from copy import deepcopy

_BASE_SCENARIOS = (
    {"id": "straight", "name": "走到目标点", "description": "向前走 80 厘米，在目标圈内停稳。", "target": [0.8, 0.0], "duration": 30},
    {"id": "turn", "name": "转弯到达", "description": "转向左前方，到达斜向目标后停稳。", "target": [0.65, 0.65], "duration": 30},
    {"id": "precision", "name": "短距离停靠", "description": "向前走 40 厘米，练习小步移动和及时停车。", "target": [0.4, 0.0], "duration": 20},
    {"id": "long_straight", "name": "远距离前行", "description": "向前走 1.5 米，在目标圈内停稳。", "target": [1.5, 0.0], "duration": 40},
    {"id": "right_turn", "name": "向右转弯", "description": "转向右前方，到达右侧斜向目标后停稳。", "target": [0.65, -0.65], "duration": 30},
    {"id": "shallow_left", "name": "左前方停靠", "description": "向前 90 厘米、左侧 35 厘米，到达目标后停稳。", "target": [0.9, 0.35], "duration": 30},
    {"id": "shallow_right", "name": "右前方停靠", "description": "向前 90 厘米、右侧 35 厘米，到达目标后停稳。", "target": [0.9, -0.35], "duration": 30},
    {"id": "wide_left", "name": "大角度左转", "description": "转向左侧，走到前方 35 厘米、左侧 90 厘米的目标。", "target": [0.35, 0.9], "duration": 35},
    {"id": "detour_left", "name": "左侧绕障", "description": "从左侧绕过挡路箱，到达箱后目标。", "target": [1.8, 0], "duration": 50,
     "target_frame": "world", "obstacles": [{"position": [.85, 0, .15], "size": [.25, .4, .3], "yaw": 0}],
     "waypoints": [[.35, .65], [1.25, .65], [1.8, 0]]},
    {"id": "detour_right", "name": "右侧绕障", "description": "从右侧绕过挡路箱，到达箱后目标。", "target": [1.8, 0], "duration": 50,
     "target_frame": "world", "obstacles": [{"position": [.85, 0, .15], "size": [.25, .4, .3], "yaw": 0}],
     "waypoints": [[.35, -.65], [1.25, -.65], [1.8, 0]]},
    {"id": "slalom", "name": "交错障碍通道", "description": "穿过交错摆放的箱子，避免接触后停稳。", "target": [2.4, 0], "duration": 60,
     "target_frame": "world", "obstacles": [{"position": [.8, -.3, .15], "size": [.25, .65, .3], "yaw": 0},
                                            {"position": [1.6, .3, .15], "size": [.25, .65, .3], "yaw": 0}],
     "waypoints": [[.35, .6], [1.1, .6], [1.25, -.6], [1.95, -.6], [2.4, 0]]},
    {"id": "corridor", "name": "直线走廊", "description": "沿两侧长墙之间前行，保持方向，到出口停稳。", "target": [2.5, 0], "duration": 50,
     "target_frame": "world", "obstacles": [{"position": [1.25, .55, .15], "size": [1.9, .16, .3], "yaw": 0},
                                            {"position": [1.25, -.55, .15], "size": [1.9, .16, .3], "yaw": 0}],
     "waypoints": [[.45, 0], [1.9, 0], [2.5, 0]]},
    {"id": "docking_bay", "name": "箱间停靠", "description": "走入两只箱子之间，在有限空间内停稳。", "target": [1.25, 0], "duration": 40,
     "target_frame": "world", "obstacles": [{"position": [1.25, .45, .15], "size": [.6, .25, .3], "yaw": 0},
                                            {"position": [1.25, -.45, .15], "size": [.6, .25, .3], "yaw": 0}],
     "waypoints": [[.45, 0], [.8, 0], [1.25, 0]]},
    {"id": "double_gate", "name": "连续双门", "description": "连续穿过两组箱子形成的门，到出口停稳。", "target": [2.5, 0], "duration": 50,
     "target_frame": "world", "obstacles": [{"position": [x, y, .15], "size": [.18, .25, .3], "yaw": 0}
                                            for x in [.8, 1.65] for y in [-.48, .48]],
     "waypoints": [[.45, 0], [1.2, 0], [1.95, 0], [2.5, 0]]},
    {"id": "island_route", "name": "长岛绕行", "description": "绕过横向延伸的长箱，沿箱侧前行，再转向箱后目标。", "target": [2.9, 0], "duration": 70,
     "target_frame": "world", "obstacles": [{"position": [1.45, 0, .15], "size": [1.15, .5, .3], "yaw": 0}],
     "waypoints": [[.35, .85], [2.3, .85], [2.9, 0]]},
    {"id": "diagonal_barrier", "name": "斜置长障碍", "description": "绕过平地上斜向摆放的长箱；这是平地绕障，不是斜坡。", "target": [2.5, 0], "duration": 60,
     "target_frame": "world", "obstacles": [{"position": [1.15, 0, .15], "size": [.25, 1.1, .3], "yaw": .45}],
     "waypoints": [[.35, .85], [1.65, .85], [2.5, 0]]},
    {"id": "offset_gates", "name": "偏置双门", "description": "通过左右错位的两道门，在门之间改变方向后停稳。", "target": [2.9, -.3], "duration": 70,
     "target_frame": "world", "obstacles": [{"position": [x, center + offset, .15], "size": [.18, .22, .3], "yaw": 0}
                                            for x, center in [[.8, .3], [2, -.3]] for offset in [-.5, .5]],
     "waypoints": [[.35, .3], [1.2, .3], [1.6, -.3], [2.4, -.3], [2.9, -.3]]},
    {"id": "gentle_ramp", "name": "缓坡上下坡", "description": "沿真实 4.3° 坡面上坡，再下坡到目标停稳；坡顶高 6 厘米。", "target": [2.3, 0], "duration": 60,
     "target_frame": "world", "terrain": [{"kind": "ramp", "position": [.8, 0, 0], "size": [.8, .8, .06], "direction": 1},
                                              {"kind": "ramp", "position": [1.6, 0, 0], "size": [.8, .8, .06], "direction": -1}],
     "waypoints": [[.35, 0], [.8, 0], [1.6, 0], [2.3, 0]]},
)

_FOOTBALL_SCENARIOS = tuple({"id": "football_" + side, "name": "左脚射门" if side == "left" else "右脚射门",
    "description": "用官方踢球策略踢真实碰撞足球，穿过前方球门线。", "task_type": "football", "skill": "kick_" + side,
    "target": [.4, 0], "target_frame": "world", "duration": 6,
    "goal": {"x": .4, "y": 0, "width": 1.0},
    "objects": [{"kind": "ball", "radius": .035, "position": [.095, .042 if side == "left" else -.042, .035]}],
    "category": "football", "difficulty": "advanced", "fast_only": True}
    for side in ("left", "right"))
_PICKUP_SCENARIOS = ({"id": "pickup_trash", "name": "物品搬运 A → B", "description": "实验性仿真夹持：捡起物品 A，搬运到 B 点并松开放稳；夹持模型尚未经过真机验证。",
    "task_type": "pickup", "skill": "ground_pick", "target": [.6, 0], "target_frame": "world", "duration": 30,
    "simulated_gripper": True, "grasp_model": "simulated-contact-gripper-v1",
    "objects": [{"id": "trash", "kind": "trash", "position": [.1, 0, .01], "size": [.02, .025, .02]}],
    "category": "pickup", "difficulty": "complex", "fast_only": True},)


_ADVANCED = {"gentle_ramp", "detour_left", "detour_right", "corridor", "docking_bay", "double_gate"}
SCENARIOS = tuple({**scene, "category": "terrain" if scene.get("terrain") else "obstacle" if scene.get("obstacles") else "navigation",
                   "difficulty": ("advanced" if scene["id"] in _ADVANCED else
                                  "complex" if scene.get("obstacles") else "simple")}
                  for scene in _BASE_SCENARIOS) + _FOOTBALL_SCENARIOS + _PICKUP_SCENARIOS


def get_scenario(scene_id):
    return next((deepcopy(scene) for scene in SCENARIOS if scene["id"] == scene_id), None)
