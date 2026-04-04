export const CHART_COLOR_ORDER = [
  'var(--chart-1)',
  'var(--chart-2)',
  'var(--chart-3)',
  'var(--chart-5)',
  'var(--chart-4)',
  'var(--chart-6)',
  'var(--chart-7)',
  'var(--chart-8)',
  'var(--chart-9)',
  'var(--chart-10)',
]

export const CHART_SURFACE_COLORS = CHART_COLOR_ORDER.map(
  (color) => `color-mix(in srgb, ${color} 78%, transparent)`
)

export const CHART_AXIS_COLOR = 'var(--chart-axis)'
export const CHART_GRID_COLOR = 'var(--chart-grid)'
export const CHART_TOOLTIP_STYLE = {
  backgroundColor: 'var(--chart-tooltip-bg)',
  borderColor: 'var(--chart-tooltip-border)',
  color: 'var(--chart-tooltip-text)',
}

export const CHART_HOVER_CURSOR = {
  fill: 'var(--chart-crosshair)',
  fillOpacity: 0.32,
}
