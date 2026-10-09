import type { SceneObject } from "./api";

/** Recorded pose takes precedence; static metadata fills older or partial frames. */
export function objectPose(item: SceneObject, reference: SceneObject[] = []) {
  const base = reference.find((candidate) => candidate.id === item.id);
  return {
    ...base,
    ...item,
    size: item.size ?? base?.size,
    radius: item.radius ?? base?.radius,
    quaternion:
      item.quaternion ??
      base?.quaternion ??
      ([1, 0, 0, 0] as [number, number, number, number]),
  };
}

export function renderQuaternion([w, x, y, z]: [
  number,
  number,
  number,
  number,
]): [number, number, number, number] {
  return [x, y, z, w];
}

export function objectIndicatorAnchor([x, y, z]: [number, number, number]): [
  number,
  number,
  number,
] {
  return [x, y, z + 0.16];
}
