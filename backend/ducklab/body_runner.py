"""Official body protocol with BAM M6 physics and world-state recording.

Pollen's Handler and sensors remain intact. BAM uses the upstream CPU policy
rehearsal loaders; --legacy selects the original XML position actuators.
"""
import argparse
import json
import sys
import threading
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rl", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--legacy", action="store_true", help="Use legacy XML position actuators")
    parser.add_argument("--scenario", default="straight")
    args = parser.parse_args()
    from .scenarios import get_scenario
    scene = get_scenario(args.scenario)
    if scene is None:
        parser.error("unknown scenario")
    if args.legacy and (scene.get("obstacles") or scene.get("terrain")):
        parser.error("obstacle and terrain scenes require BAM physics")
    sys.path.insert(0, str(args.rl / "src"))
    import mujoco
    from mjlab_microduck.sim.body_server import Body, World, Server, Handler, DEFAULT_SCENE, pose_table

    if args.legacy:
        world = World(DEFAULT_SCENE)
        body = Body(world, 0)
        pose, height = pose_table(DEFAULT_SCENE, "SIT")
        body.place(pose, height, 0.0)
        world.bodies.append(body)
        mujoco.mj_forward(world.model, world.data)
    else:
        from .bam_body import create_body
        world, body = create_body(args.rl, scene)
    server = Server(("127.0.0.1", args.port), Handler)
    server.body = body
    threading.Thread(target=server.serve_forever, daemon=True).start()
    obstacle_geoms = {
        i for i in range(world.model.ngeom)
        if world.model.geom_bodyid[i] == 0 and world.model.geom_type[i] != mujoco.mjtGeom.mjGEOM_PLANE and not (mujoco.mj_id2name(world.model, mujoco.mjtObj.mjOBJ_GEOM, i) or '').startswith('ducklab_terrain_')
    }
    due = time.perf_counter()
    try:
        while True:
            world.step(4)
            sensors = body.sensors()
            with world.lock:
                collisions = sum(
                    1 for contact in world.data.contact[:world.data.ncon]
                    if int(contact.geom1) in obstacle_geoms or int(contact.geom2) in obstacle_geoms
                )
            collisions = max(collisions, getattr(world, "last_collisions", 0))
            gravity = sensors["imu"]["gravity"]
            frame = {"type": "frame", "t": sensors["sim_time"], "position": sensors["trunk"],
                     "quaternion": sensors["imu"]["quat"], "joints": sensors["positions"],
                     "fallen": gravity[2] > -0.4, "collisions": collisions}
            print(json.dumps(frame, allow_nan=False), flush=True)
            due += 0.020
            slack = due - time.perf_counter()
            if slack > 0:
                time.sleep(slack)
            elif slack < -0.25:
                print("physics behind real time", file=sys.stderr, flush=True)
                due = time.perf_counter()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
