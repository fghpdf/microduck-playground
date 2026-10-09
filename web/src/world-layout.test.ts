import { describe, expect, it } from "vitest";
import { worldLayout, viewDistance, rampVertices } from "./world-layout";

describe("scene framing", () => {
  it("includes long goals and rotated obstacle extents", () => {
    const box = {
      position: [3, 1, 0.2] as [number, number, number],
      size: [2, 0.4, 0.4] as [number, number, number],
      yaw: Math.PI / 2,
    };
    const layout = worldLayout([2.4, 0], [box]);
    for (const point of [
      [3.2, 2, 0.4],
      [-0.35, -0.35, 0],
      [2.65, 0.25, 0],
    ]) {
      expect(
        Math.hypot(...point.map((v, i) => v - layout.center[i])),
      ).toBeLessThanOrEqual(layout.radius);
    }
  });
  it("keeps small scenes close and fits larger and narrower views", () => {
    expect(viewDistance(worldLayout([0.4, 0]).radius, 1.5)).toBe(3.4);
    const radius = worldLayout([2.4, 0]).radius;
    expect(viewDistance(radius, 1.5)).toBeGreaterThan(3.4);
    expect(viewDistance(radius, 0.5)).toBeGreaterThan(
      viewDistance(radius, 1.5),
    );
  });
});

describe("ramp terrain", () => {
  it("matches the physical triangular prism in both travel directions", () => {
    const ramp = {
      kind: "ramp" as const,
      position: [2, 1, 0] as [number, number, number],
      size: [0.8, 0.8, 0.06] as [number, number, number],
      direction: 1 as const,
    };
    expect(rampVertices(ramp)).toContainEqual([2.4, 0.6, 0.06]);
    expect(rampVertices(ramp)).toContainEqual([1.6, 0.6, 0]);
    expect(rampVertices({ ...ramp, direction: -1 })).toContainEqual([
      1.6, 0.6, 0.06,
    ]);
    const layout = worldLayout([0.4, 0], [], [ramp]);
    for (const point of rampVertices(ramp)) {
      expect(
        Math.hypot(...point.map((v, i) => v - layout.center[i])),
      ).toBeLessThanOrEqual(layout.radius);
    }
  });
});

it("keeps the complete ball trajectory inside playback framing", () => {
  const paths: [number, number, number][] = [
    [0.1, 0, 0.035],
    [4.3, 0.5, 0.035],
  ];
  const layout = worldLayout([0.4, 0], [], [], paths);
  for (const point of paths)
    expect(
      Math.hypot(...point.map((v, i) => v - layout.center[i])),
    ).toBeLessThanOrEqual(layout.radius);
  expect(layout.radius).toBeGreaterThan(2);
});
