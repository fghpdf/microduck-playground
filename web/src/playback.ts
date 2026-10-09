/** Select recorded state by elapsed wall time, skipping frames when rendering is slower. */
export function playbackFrameIndex(
  frames: readonly { t: number }[],
  startTime: number,
  elapsedMs: number,
  speed: number,
): number {
  const target = startTime + (Math.max(0, elapsedMs) * speed) / 1000;
  let low = 0;
  let high = frames.length;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (frames[middle].t <= target) low = middle + 1;
    else high = middle;
  }
  return Math.max(0, low - 1);
}
