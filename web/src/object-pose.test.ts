import { it, expect } from "vitest";
import { objectPose } from "./object-pose";

it("preserves measured trash rotation and dimensions while filling missing metadata", () => {
  const recorded = {
    id: "trash",
    kind: "trash" as const,
    position: [0.4, 0, 0.02] as [number, number, number],
    quaternion: [0.707, 0, 0.707, 0] as [number, number, number, number],
  };
  const reference = {
    ...recorded,
    position: [0.1, 0, 0.01] as [number, number, number],
    quaternion: [1, 0, 0, 0] as [number, number, number, number],
    size: [0.02, 0.025, 0.02] as [number, number, number],
  };
  expect(objectPose(recorded, [reference])).toEqual({
    ...recorded,
    size: reference.size,
    radius: undefined,
  });
  expect(
    objectPose({ ...recorded, quaternion: undefined }, []).quaternion,
  ).toEqual([1, 0, 0, 0]);
});

it("converts the measured MuJoCo wxyz pose into renderer xyzw order", async () => {
  const { renderQuaternion } = await import("./object-pose");
  expect(renderQuaternion([0.707, 0, 0.707, 0])).toEqual([0, 0.707, 0, 0.707]);
});

it("anchors the visibility indicator to the measured moving object without changing its pose", async () => {
  const { objectIndicatorAnchor } = await import("./object-pose");
  const position: [number, number, number] = [0.5, 0.03, 0.14];
  expect(objectIndicatorAnchor(position)).toEqual([
    0.5, 0.03, 0.30000000000000004,
  ]);
  expect(position).toEqual([0.5, 0.03, 0.14]);
});
