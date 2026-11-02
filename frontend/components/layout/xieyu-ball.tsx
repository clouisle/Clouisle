'use client'

import * as React from 'react'

export type XieyuOrbState = 'idle' | 'listening' | 'thinking' | 'working' | 'waiting' | 'success' | 'error'

interface XieyuBallProps {
  state?: XieyuOrbState
  responseKey?: number
  focused?: boolean
}

export function XieyuBall({ state = 'idle', responseKey = 0, focused = false }: XieyuBallProps) {
  const orbRef = React.useRef<SVGSVGElement>(null)
  const [responding, setResponding] = React.useState(false)
  const [looking, setLooking] = React.useState(false)
  const gradientId = React.useId().replace(/:/g, '')

  React.useEffect(() => {
    if (!responseKey || state !== 'idle') {
      setResponding(false)
      return
    }
    setResponding(true)
    const timeout = window.setTimeout(() => setResponding(false), 700)
    return () => window.clearTimeout(timeout)
  }, [responseKey, state])

  React.useEffect(() => {
    if (state !== 'idle') return
    const orb = orbRef.current
    if (!orb) return
    const desktop = window.matchMedia('(min-width: 1024px)')
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)')
    const reset = () => {
      orb.style.removeProperty('--gaze-x')
      orb.style.removeProperty('--gaze-y')
      setLooking(false)
    }
    const move = (event: PointerEvent) => {
      const rect = orb.getBoundingClientRect()
      const x = Math.max(-1, Math.min(1, (event.clientX - rect.left - rect.width / 2) / (window.innerWidth / 2)))
      const y = Math.max(-1, Math.min(1, (event.clientY - rect.top - rect.height / 2) / (window.innerHeight / 2)))
      orb.style.setProperty('--gaze-x', `${x * 5}px`)
      orb.style.setProperty('--gaze-y', `${y * 3}px`)
      setLooking(true)
    }
    const leave = (event: PointerEvent) => { if (!event.relatedTarget) reset() }
    const update = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerout', leave)
      reset()
      if (desktop.matches && !reduced.matches) {
        window.addEventListener('pointermove', move, { passive: true })
        window.addEventListener('pointerout', leave)
      }
    }
    desktop.addEventListener('change', update)
    reduced.addEventListener('change', update)
    update()
    return () => {
      desktop.removeEventListener('change', update)
      orb.style.removeProperty('--gaze-x')
      orb.style.removeProperty('--gaze-y')
      reduced.removeEventListener('change', update)
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerout', leave)
    }
  }, [state])

  const expression = state !== 'idle' ? state : responding ? 'responding' : focused ? 'focused' : looking ? 'looking' : 'idle'

  return (
    <svg ref={orbRef} className="xieyu-orb" data-expression={expression} viewBox="0 0 100 100" aria-hidden="true">
      <defs>
        <radialGradient id={gradientId} cx="30%" cy="24%" r="80%">
          <stop offset="0%" stopColor="color-mix(in oklch, var(--primary) 18%, white)" />
          <stop offset="48%" stopColor="color-mix(in oklch, var(--primary) 52%, white)" />
          <stop offset="100%" stopColor="color-mix(in oklch, var(--primary) 72%, #31545a)" />
        </radialGradient>
      </defs>
      <g key={expression === 'responding' ? responseKey : 'body'} className="xieyu-body">
        <circle cx="50" cy="50" r="44" fill={`url(#${gradientId})`} />
        <ellipse cx="35" cy="25" rx="19" ry="9" fill="#fff" opacity=".23" transform="rotate(-27 35 25)" />
        <g className="xieyu-eyes">
          <g className="xieyu-eye xieyu-eye-left"><ellipse cx="39" cy="47" rx="5.5" ry="9" /></g>
          <g className="xieyu-eye xieyu-eye-right"><ellipse cx="61" cy="47" rx="5.5" ry="9" /></g>
        </g>
        <path className="xieyu-smile" d="M41 61 Q50 69 59 61" />
      </g>
      <ellipse className="xieyu-orbit" cx="50" cy="50" rx="48" ry="15" />
    </svg>
  )
}
