import { describe, expect, it } from "vitest";
import { playbackFrameIndex } from "./playback";
describe("wall-clock playback", () => {
  const frames = Array.from({ length: 501 }, (_, i) => ({ t: i / 50 }));
  it.each([0.5, 1, 2, 8])(
    "advances at %sx regardless of render frequency",
    (speed) => {
      expect(playbackFrameIndex(frames, 0, 1000, speed)).toBe(speed * 50);
      expect(playbackFrameIndex(frames, 0, 1000, speed)).toBe(
        playbackFrameIndex(frames, 0, 1000, speed),
      );
    },
  );
  it("anchors a speed change at the current simulated time", () => {
    expect(playbackFrameIndex(frames, 3, 0, 8)).toBe(150);
    expect(playbackFrameIndex(frames, 3, 250, 8)).toBe(250);
  });
  it("handles irregular timestamps and clamps to the final frame", () => {
    expect(
      playbackFrameIndex([{ t: 0 }, { t: 0.3 }, { t: 1 }], 0, 500, 1),
    ).toBe(1);
    expect(playbackFrameIndex(frames, 9, 1000, 8)).toBe(500);
    expect(playbackFrameIndex([], 0, 1000, 1)).toBe(0);
  });
});
