/**
 * Structural shape of a server-reported progress tick, so callers do not need to
 * import the chat part types.
 */
export interface ToolProgressLike {
  progress: number
  total?: number | null
}

/**
 * Completed percentage for a determinate progress tick, or null when there is
 * nothing honest to show. Every place that renders tool progress goes through
 * here so the header, the trace step, and the legacy card cannot drift apart.
 *
 * Rule: a percentage is only meaningful when the server reported a positive
 * total. An indeterminate tool, a missing tick, or a zero/NaN total renders
 * nothing rather than a misleading 0%.
 */
export function getToolProgressPercent(
  progress: ToolProgressLike | undefined | null
): number | null {
  const total = progress?.total
  if (typeof total !== 'number' || !Number.isFinite(total) || total <= 0) {
    return null
  }
  const ratio = (progress?.progress ?? 0) / total
  return Math.min(100, Math.max(0, Math.round(ratio * 100)))
}
