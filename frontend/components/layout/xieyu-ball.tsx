'use client'

import * as React from 'react'
import { initializeGrokBall, type GrokBallApi, type GrokBallEngine } from '@/vendor/grok-ball/grok-ball.js'

export type XieyuOrbState = 'idle' | 'listening' | 'thinking' | 'working' | 'waiting' | 'success' | 'error'

interface XieyuBallProps {
  state?: XieyuOrbState
  responseKey?: number
  focused?: boolean
}

const EMOTIONS: Record<XieyuOrbState, string> = {
  idle: '02', listening: '35', thinking: '30', working: '32', waiting: '35', success: '33', error: '34',
}


let grokBall: GrokBallApi | undefined

export function XieyuBall({ state = 'idle', responseKey = 0, focused = false }: XieyuBallProps) {
  const orbRef = React.useRef<HTMLSpanElement>(null)
  const engineRef = React.useRef<GrokBallEngine | null>(null)
  const stateRef = React.useRef(state)
  const focusedRef = React.useRef(focused)
  const motionRef = React.useRef(false)

  React.useEffect(() => {
    stateRef.current = state
    focusedRef.current = focused
    const engine = engineRef.current
    if (!engine) return
    const emotion = state === 'idle' && focused ? '03' : EMOTIONS[state]
    if (engine.emotionId !== emotion) {
      engine.setEmotion(emotion)
    }
  }, [state, focused])

  React.useEffect(() => {
    if (responseKey && stateRef.current === 'idle' && motionRef.current) engineRef.current?.spin()
  }, [responseKey])

  React.useEffect(() => {
    const orb = orbRef.current
    if (!orb) return
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)')
    const move = (event: PointerEvent) => {
      if (stateRef.current !== 'idle') return
      const rect = orb.getBoundingClientRect()
      engineRef.current?.setGaze(
        (event.clientX - rect.left - rect.width / 2) / (window.innerWidth / 2),
        (event.clientY - rect.top - rect.height / 2) / (window.innerHeight / 2),
      )
    }
    const leave = (event: PointerEvent) => { if (!event.relatedTarget) engineRef.current?.clearGaze() }
    const update = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerout', leave)
      engineRef.current?.destroy()
      engineRef.current = null
      motionRef.current = !reduced.matches
      grokBall ??= initializeGrokBall()
      const emotion = stateRef.current === 'idle' && focusedRef.current ? '03' : EMOTIONS[stateRef.current]
      engineRef.current = grokBall.create(orb, { emotion, color: '#b9dcea', eyeColor: '#263f56', autostart: motionRef.current })
      if (motionRef.current) {
        window.addEventListener('pointermove', move, { passive: true })
        window.addEventListener('pointerout', leave)
      }
    }
    reduced.addEventListener('change', update)
    update()
    return () => {
      reduced.removeEventListener('change', update)
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerout', leave)
      engineRef.current?.destroy()
      engineRef.current = null
    }
  }, [])

  return <span ref={orbRef} className="xieyu-orb" aria-hidden="true" />
}
