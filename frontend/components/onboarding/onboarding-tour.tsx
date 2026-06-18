'use client'

import * as React from 'react'
import {
  Joyride,
  ACTIONS,
  EVENTS,
  STATUS,
  type EventData,
  type Controls,
} from 'react-joyride'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/button'
import { useOnboarding, type OnboardingTourId } from './onboarding-provider'
import { getTourConfigById, allTourConfigs } from './steps/platform-steps'
import type { OnboardingStep } from './steps/types'

interface OnboardingTourProps {
  tourId: OnboardingTourId
}

// Custom CSS styles for the tooltip
const tooltipStyles: React.CSSProperties = {
  borderRadius: '8px',
  border: '1px solid #e5e7eb',
  boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)',
  padding: '16px',
  maxWidth: '360px',
  backgroundColor: '#ffffff',
  color: '#111827',
}

// CSS to make overlay pass-through clicks when on dialog steps
// The overlay is still visible but clicks go through to the dialog
const joyrideDialogOverlayFix = `
  body.joyride-dialog-active .react-joyride__overlay {
    pointer-events: none !important;
  }
`

const tooltipTitleStyles: React.CSSProperties = {
  fontSize: '15px',
  fontWeight: '600',
  marginBottom: '8px',
  color: '#111827',
}

const tooltipContentStyles: React.CSSProperties = {
  fontSize: '14px',
  lineHeight: '1.5',
  color: '#6b7280',
}

const tooltipFooterStyles: React.CSSProperties = {
  marginTop: '16px',
  padding: '0',
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
}

function getTourConfig(tourId: OnboardingTourId) {
  return getTourConfigById(tourId) || null
}

function targetExists(step: OnboardingStep | undefined) {
  const target = step?.target
  if (typeof target !== 'string') return true
  return document.querySelector(target) !== null
}

function findStartingStep(steps: OnboardingStep[]) {
  return steps.findIndex(step => targetExists(step))
}

function routeMatches(pathname: string, route: string) {
  if (pathname === route) return true
  if (route === '/app') return false
  return pathname.startsWith(`${route}/`)
}

// Export all tour IDs for rendering
export const allTourIds: OnboardingTourId[] = allTourConfigs.map(c => c.id)

export function OnboardingTour({ tourId }: OnboardingTourProps) {
  const t = useTranslations()
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const pathnameRef = React.useRef(pathname)
  const { state, startTour, nextStep, goToStep, completeTour } = useOnboarding()
  const controlsRef = React.useRef<Controls | null>(null)
  const hasAutoStarted = React.useRef(false)
  const urlTriggeredRef = React.useRef(false)
  const advanceTriggeredRef = React.useRef(false)

  // Keep pathnameRef in sync with latest pathname
  React.useEffect(() => {
    pathnameRef.current = pathname
  }, [pathname])

  const config = getTourConfig(tourId)

  // Auto-start tour for new users on the home page
  React.useEffect(() => {
    if (
      tourId === 'overview' &&
      config?.autoStart &&
      !state.isRunning &&
      !state.completedTours.includes('overview') &&
      pathname === '/app' &&
      !hasAutoStarted.current
    ) {
      hasAutoStarted.current = true
      // Small delay to ensure the page is fully loaded
      const timer = setTimeout(() => {
        startTour('overview')
      }, 500)
      return () => clearTimeout(timer)
    }
  }, [tourId, config, state.isRunning, state.completedTours, pathname, startTour])

  // Get all steps (no filtering by route)
  const steps = React.useMemo(() => {
    if (!config) return []
    return config.steps
  }, [config])

  // Allow external links to trigger tours, e.g. /app/apps?tour=appCreate or
  // /app/apps/:id?tour=appConfig&step=1.
  React.useEffect(() => {
    if (!config || urlTriggeredRef.current) return

    const requestedTour = searchParams.get('tour')
    if (requestedTour !== tourId) return

    const requestedStep = Number(searchParams.get('step') || '0')
    const initialStep = Number.isInteger(requestedStep)
      ? Math.min(Math.max(requestedStep, 0), Math.max(steps.length - 1, 0))
      : 0

    urlTriggeredRef.current = true
    startTour(tourId, initialStep)
  }, [config, searchParams, startTour, steps.length, tourId])

  // Detect the best starting step when a tour starts, then jump to it
  const startingStepDetectedRef = React.useRef<OnboardingTourId | null>(null)
  React.useEffect(() => {
    if (!state.isRunning || state.currentTour !== tourId) {
      if (startingStepDetectedRef.current === tourId) {
        startingStepDetectedRef.current = null
      }
      return
    }

    if (startingStepDetectedRef.current === tourId) return

    // Delay to allow page transitions/animations to settle
    const timer = setTimeout(() => {
      if (startingStepDetectedRef.current === tourId) return
      startingStepDetectedRef.current = tourId

      const startIdx = findStartingStep(steps)
      if (startIdx > 0 && state.currentStep === 0) {
        goToStep(startIdx)
      }
    }, 300)

    return () => clearTimeout(timer)
  }, [state.isRunning, state.currentTour, tourId, state.currentStep, steps, goToStep])

  // Current step index
  const currentStepIndex = state.currentStep

  // Get current step data
  const currentStep = steps[currentStepIndex]

  const handleJoyrideEvent = React.useCallback(
    (data: EventData, controls: Controls) => {
      const { action, type } = data

      // Store controls reference
      controlsRef.current = controls

      if (type === EVENTS.STEP_AFTER) {
        // Only handle NEXT action from Joyride
        // PREV is handled by our custom back button
        if (action === ACTIONS.NEXT) {
          // Check if next step requires navigation
          const nextStepIndex = currentStepIndex + 1
          const nextStepData = steps[nextStepIndex]

          if (nextStepData?.route) {
            // Use exact matching for route check
            const isOnCorrectRoute = routeMatches(pathname, nextStepData.route)
            if (!isOnCorrectRoute) {
              // Navigate first, then advance step
              router.push(nextStepData.route)
              setTimeout(() => {
                nextStep()
              }, 500)
            } else {
              nextStep()
            }
          } else {
            nextStep()
          }
        }
      }

      // Handle TARGET_NOT_FOUND: wait for drawer/menu elements to render
      if (type === EVENTS.TARGET_NOT_FOUND) {
        if (action === ACTIONS.NEXT) {
          // Wait 500ms for drawer/menu elements to render
          setTimeout(() => {
            const nextStepIndex = currentStepIndex + 1
            const nextStepData = steps[nextStepIndex]

            if (nextStepData) {
              // Check if the target element exists in DOM
              const target = nextStepData.target
              const targetExists = typeof target === 'string'
                ? !!document.querySelector(target)
                : !!target
              if (targetExists) {
                if (nextStepData.route) {
                  const isOnCorrectRoute = routeMatches(pathname, nextStepData.route)
                  if (!isOnCorrectRoute) {
                    router.push(nextStepData.route)
                    setTimeout(() => {
                      nextStep()
                    }, 500)
                  } else {
                    nextStep()
                  }
                } else {
                  nextStep()
                }
              } else {
                // Target still not found, skip this step
                if (nextStepIndex < steps.length - 1) {
                  nextStep()
                } else {
                  completeTour(tourId)
                }
              }
            }
          }, 500)
        }
      }

      if (data.status === STATUS.FINISHED || data.status === STATUS.SKIPPED) {
        completeTour(tourId)
      }
    },
    [steps, currentStepIndex, pathname, router, nextStep, completeTour, tourId]
  )

  // Handle navigation when step changes and requires a different route
  React.useEffect(() => {
    if (!state.isRunning || state.currentTour !== tourId || !currentStep?.route) return

    // Pure navigation steps should wait for the user to click the highlighted
    // nav item. Their route is used by the click handler to detect completion,
    // not for automatic navigation.
    if (currentStep.advanceOnClick && currentStep.waitForRouteChange) return

    // Use strict equality so /app does not match /app/models etc.
    if (pathname !== currentStep.route) {
      router.push(currentStep.route)
    }
  }, [state.isRunning, state.currentTour, tourId, currentStep, pathname, router])

  const handleNext = React.useCallback(() => {
    if (currentStepIndex < steps.length - 1) {
      nextStep()
    } else {
      completeTour(tourId)
    }
  }, [currentStepIndex, steps.length, nextStep, completeTour, tourId])

  // Keyboard shortcut: Ctrl+Enter to advance (only when Next button is visible)
  React.useEffect(() => {
    if (!state.isRunning || state.currentTour !== tourId) return

    // Check if current step should hide the Next button
    const isAdvanceOnClick = currentStep?.advanceOnClick
    const isAdvanceOnInput = currentStep?.advanceOnInput
    const shouldHideNextButton = isAdvanceOnClick || isAdvanceOnInput

    // Only enable shortcut if Next button is visible
    if (shouldHideNextButton) return

    const handleKeyDown = (e: KeyboardEvent) => {
      // Ignore if focus is in an input, textarea, or contenteditable element
      const activeElement = document.activeElement
      const isInputFocused =
        activeElement?.tagName === 'INPUT' ||
        activeElement?.tagName === 'TEXTAREA' ||
        activeElement?.getAttribute('contenteditable') === 'true'

      if (isInputFocused) return

      // Ctrl/⌘+Enter triggers next step
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault()
        handleNext()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [state.isRunning, state.currentTour, tourId, currentStep, handleNext])

  // Handle advanceOnClick: listen for clicks on the target element
  React.useEffect(() => {
    if (!state.isRunning || state.currentTour !== tourId || !currentStep?.advanceOnClick) return

    const target = currentStep.target
    if (typeof target !== 'string') return

    let isMounted = true
    const timers: ReturnType<typeof setTimeout>[] = []
    const schedule = (callback: () => void, delay: number) => {
      const timer = setTimeout(callback, delay)
      timers.push(timer)
      return timer
    }

    // Reset advance flag when step changes
    advanceTriggeredRef.current = false

    // Wait a bit for the element to appear
    const findAndBind = () => {
      const element = document.querySelector(target)
      if (!element) return

      const handleClick = () => {
        // Prevent multiple advances for the same step
        if (!isMounted || advanceTriggeredRef.current) return
        advanceTriggeredRef.current = true

        // If waitForRouteChange is set, wait until the expected route is reached before advancing
        if (currentStep.waitForRouteChange) {
          const originalPathname = pathnameRef.current
          let elapsed = 0
          const maxWait = 10000 // 10 seconds max wait
          const checkRouteChange = () => {
            if (!isMounted) return
            const reachedExpectedRoute = currentStep.route
              ? routeMatches(pathnameRef.current, currentStep.route)
              : pathnameRef.current !== originalPathname

            if (reachedExpectedRoute) {
              // Route reached/changed, now advance
              handleNext()
            } else if (elapsed < maxWait) {
              // Keep checking
              elapsed += 200
              schedule(checkRouteChange, 200)
            } else {
              // Timeout - just advance anyway
              handleNext()
            }
          }
          // Start checking after a short delay (to let the click action start)
          schedule(checkRouteChange, 300)
        } else {
          // Small delay to let the click action happen first (e.g., open a dialog)
          schedule(() => {
            if (!isMounted) return
            handleNext()
          }, 300)
        }
      }

      element.addEventListener('click', handleClick)
      return () => element.removeEventListener('click', handleClick)
    }

    // Try immediately, then retry after a short delay if not found
    let cleanup = findAndBind()
    if (!cleanup) {
      schedule(() => {
        if (!isMounted) return
        cleanup = findAndBind()
      }, 500)
    }
    return () => {
      isMounted = false
      timers.forEach(clearTimeout)
      cleanup?.()
    }
  }, [state.isRunning, state.currentTour, tourId, currentStep, handleNext, currentStepIndex])

  // Handle advanceOnInput: listen for input events on the target element
  React.useEffect(() => {
    if (!state.isRunning || state.currentTour !== tourId || !currentStep?.advanceOnInput) return

    const target = currentStep.target
    if (typeof target !== 'string') return

    // Reset advance flag when step changes
    advanceTriggeredRef.current = false

    // Wait a bit for the element to appear
    const findAndBind = () => {
      const element = document.querySelector(target) as HTMLInputElement | null
      if (!element) return

      const handleInput = () => {
        // Prevent multiple advances for the same step
        if (advanceTriggeredRef.current) return
        // Advance when user types something
        if (element.value.trim().length > 0) {
          advanceTriggeredRef.current = true
          setTimeout(() => {
            handleNext()
          }, 300)
        }
      }

      element.addEventListener('input', handleInput)
      return () => element.removeEventListener('input', handleInput)
    }

    // Try immediately, then retry after a short delay if not found
    let cleanup = findAndBind()
    if (!cleanup) {
      const timer = setTimeout(() => {
        cleanup = findAndBind()
      }, 500)
      return () => {
        clearTimeout(timer)
        cleanup?.()
      }
    }
    return cleanup
  }, [state.isRunning, state.currentTour, tourId, currentStep, handleNext, currentStepIndex])

  const handleSkip = React.useCallback(() => {
    completeTour(tourId)
  }, [completeTour, tourId])

  // Add body class when on dialog steps to make overlay pass-through clicks
  // This effect must be before early returns to maintain hook order
  const targetSelector = typeof currentStep?.target === 'string' ? currentStep.target : ''
  const isDialogStep = state.isRunning && state.currentTour === tourId && targetSelector && (
    targetSelector.includes('app-create-type-selector') ||
    targetSelector.includes('app-create-name-input') ||
    targetSelector.includes('app-create-description-input') ||
    targetSelector.includes('app-create-submit')
  )

  React.useEffect(() => {
    if (isDialogStep) {
      document.body.classList.add('joyride-dialog-active')
    } else {
      document.body.classList.remove('joyride-dialog-active')
    }
    return () => {
      document.body.classList.remove('joyride-dialog-active')
    }
  }, [isDialogStep])

  if (!config || state.currentTour !== tourId || !state.isRunning) {
    return null
  }

  if (steps.length === 0) {
    return null
  }

  return (
    <>
      <style>{joyrideDialogOverlayFix}</style>
      <Joyride
      steps={steps}
      stepIndex={currentStepIndex}
      run={state.isRunning && state.currentTour === tourId}
      continuous
      scrollToFirstStep
      options={{
        showProgress: true,
        skipBeacon: true,
        overlayClickAction: 'close',
        dismissKeyAction: false,
        primaryColor: '#3b82f6',
        backgroundColor: '#ffffff',
        textColor: '#111827',
        overlayColor: 'rgba(0, 0, 0, 0.5)',
        arrowColor: '#ffffff',
        zIndex: 10000,
        scrollDuration: 300,
        scrollOffset: 200,
      }}
      onEvent={handleJoyrideEvent}
      tooltipComponent={({
        index,
        isLastStep: tooltipIsLastStep,
        step,
        size,
      }) => {
        const currentOnboardingStep = steps[currentStepIndex] as OnboardingStep | undefined
        const isAdvanceOnClick = currentOnboardingStep?.advanceOnClick
        const isAdvanceOnInput = currentOnboardingStep?.advanceOnInput
        const shouldHideNextButton = isAdvanceOnClick || isAdvanceOnInput
        return (
        <div style={tooltipStyles}>
          {step.title && (
            <div style={tooltipTitleStyles}>
              {typeof step.title === 'string' ? t(step.title) : step.title}
            </div>
          )}
          <div style={tooltipContentStyles}>
            {typeof step.content === 'string' ? t(step.content) : step.content}
          </div>
          <div style={tooltipFooterStyles}>
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">
                {index + 1} / {size}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={handleSkip}>
                {t('onboarding.skip')}
              </Button>
              {!shouldHideNextButton && (
                <Button size="sm" onClick={handleNext}>
                  {tooltipIsLastStep
                    ? t('onboarding.finish')
                    : t('onboarding.next')}
                  <kbd className="ml-1.5 rounded border border-current/20 bg-current/5 px-1 py-0.5 font-mono text-[10px] opacity-60">⌘↵</kbd>
                </Button>
              )}
            </div>
          </div>
        </div>
        )
      }}
    />
    </>
  )
}
