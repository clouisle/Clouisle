import type { Viewport } from 'next'
import type { ReactNode } from 'react'

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  interactiveWidget: 'resizes-content',
}

export default function ColslandLayout({ children }: { children: ReactNode }) {
  return children
}
