'use client'

import * as React from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { ColslandBall } from './colsland-ball'
import { cn } from '@/lib/utils'

interface ColslandTransitionContextValue {
  registerAnchor: (node: HTMLElement | null) => void
  registerPage: (visible: boolean) => void
  enter: (animate: boolean) => void
}

const ColslandTransitionContext = React.createContext<ColslandTransitionContextValue | null>(null)

export function useColslandTransition() {
  const context = React.useContext(ColslandTransitionContext)
  if (!context) throw new Error('ColslandTransitionProvider is required')
  return context
}

export function ColslandTransitionProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const t = useTranslations('platform')
  const [anchor, setAnchor] = React.useState<HTMLElement | null>(null)
  const [point, setPoint] = React.useState({ x: 0, y: 0 })
  const [pageVisible, setPageVisible] = React.useState(false)
  const [focused, setFocused] = React.useState(false)
  const [response, setResponse] = React.useState(0)
  const [rippling, setRippling] = React.useState(false)
  const [flying, setFlying] = React.useState(false)
  const [departing, setDeparting] = React.useState(false)
  const timer = React.useRef<ReturnType<typeof setTimeout> | null>(null)
  const departurePath = React.useRef<string | null>(null)
  const isPage = pathname === '/colsland'

  React.useLayoutEffect(() => {
    if (!anchor) return
    const update = () => {
      const rect = anchor.getBoundingClientRect()
      if (rect.width) setPoint({ x: rect.left + rect.width / 2 - 26, y: rect.top + 7 })
    }
    update()
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(update)
    observer?.observe(anchor)
    return () => {
      window.removeEventListener('resize', update)
      window.removeEventListener('scroll', update, true)
      observer?.disconnect()
    }
  }, [anchor])

  React.useEffect(() => {
    clearTimeout(timer.current ?? undefined)
    timer.current = null
    setRippling(false)
    if (pathname !== '/colsland' && pathname !== departurePath.current) {
      setDeparting(false)
      setFlying(false)
      departurePath.current = null
    }
  }, [pathname])

  React.useEffect(() => () => { clearTimeout(timer.current ?? undefined) }, [])

  const enter = React.useCallback((animate: boolean) => {
    if (isPage || timer.current || departing) return
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    departurePath.current = pathname
    if (!animate || reduced) {
      setFlying(false)
      router.push('/colsland')
      return
    }
    setResponse(value => value + 1)
    setRippling(true)
    timer.current = setTimeout(() => {
      timer.current = null
      setFlying(true)
      setDeparting(true)
      router.push('/colsland')
    }, 480)
  }, [departing, isPage, pathname, router])

  const context = React.useMemo(() => ({ registerAnchor: setAnchor, registerPage: setPageVisible, enter }), [enter])
  const visible = isPage ? pageVisible || departing : Boolean(anchor) || departing
  const corner = isPage && pageVisible

  return (
    <ColslandTransitionContext.Provider value={context}>
      {children}
      {visible && (
        <div className={cn('colsland-positioner', corner ? 'colsland-positioner-corner' : 'colsland-positioner-nav', flying && 'colsland-positioner-flying')}
          style={{ '--colsland-x': `${point.x}px`, '--colsland-y': `${point.y}px` } as React.CSSProperties}>
          <button type="button" data-testid="nav-colsland" aria-label={t('nav.colsland')} aria-current={corner ? 'page' : undefined}
            onClick={() => enter(true)} onPointerEnter={() => setFocused(true)} onPointerLeave={() => setFocused(false)}
            onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}>
            {rippling && <span className="colsland-ripple" data-testid="colsland-ripple" aria-hidden="true" />}
            <ColslandBall focused={focused && !corner} responseKey={response} />
          </button>
        </div>
      )}
    </ColslandTransitionContext.Provider>
  )
}
