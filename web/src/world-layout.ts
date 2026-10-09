import type { Obstacle, Terrain } from "./api";

export function rampVertices(ramp: Terrain): [number, number, number][] {
  const [cx, cy, base] = ramp.position;
  const [length, width, height] = ramp.size;
  const low = cx - (ramp.direction * length) / 2;
  const high = cx + (ramp.direction * length) / 2;
  return [
    [low, cy - width / 2, base],
    [high, cy - width / 2, base],
    [high, cy - width / 2, base + height],
    [low, cy + width / 2, base],
    [high, cy + width / 2, base],
    [high, cy + width / 2, base + height],
  ];
}

/** Bounds include the robot at the origin, the goal ring and rotated box corners. */
export function worldLayout(
  target?: [number, number],
  obstacles: Obstacle[] = [],
  terrain: Terrain[] = [],
  objectPathPoints: [number, number, number][] = [],
) {
  const points: [number, number, number][] = [
    [-0.35, -0.35, 0],
    [0.35, 0.35, 0.6],
  ];
  const goal = target ?? [1, 0];
  points.push(
    [goal[0] - 0.25, goal[1] - 0.25, 0],
    [goal[0] + 0.25, goal[1] + 0.25, 0],
  );
  for (const box of obstacles) {
    for (const x of [-box.size[0] / 2, box.size[0] / 2]) {
      for (const y of [-box.size[1] / 2, box.size[1] / 2]) {
        for (const z of [-box.size[2] / 2, box.size[2] / 2]) {
          points.push([
            box.position[0] + x * Math.cos(box.yaw) - y * Math.sin(box.yaw),
            box.position[1] + x * Math.sin(box.yaw) + y * Math.cos(box.yaw),
            box.position[2] + z,
          ]);
        }
      }
    }
  }
  points.push(...terrain.flatMap(rampVertices), ...objectPathPoints);
  const min = [0, 1, 2].map((axis) =>
    Math.min(...points.map((point) => point[axis])),
  );
  const max = [0, 1, 2].map((axis) =>
    Math.max(...points.map((point) => point[axis])),
  );
  const center = min.map((value, axis) => (value + max[axis]) / 2) as [
    number,
    number,
    number,
  ];
  const radius = Math.max(
    0.65,
    Math.hypot(...max.map((value, axis) => (value - min[axis]) / 2)),
  );
  return { center, radius };
}

export function viewDistance(radius: number, aspect: number) {
  const vertical = (38 * Math.PI) / 180;
  const horizontal =
    2 * Math.atan(Math.tan(vertical / 2) * Math.max(aspect, 0.1));
  return Math.max(
    3.4,
    (radius / Math.sin(Math.min(vertical, horizontal) / 2)) * 1.12,
  );
}
