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
import { usePathname, useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/button'
import { useOnboarding, type OnboardingTourId } from './onboarding-provider'
import { platformTourConfig, getPlatformStepsForRoute } from './steps/platform-steps'

interface OnboardingTourProps {
  tourId: OnboardingTourId
}

// Custom CSS styles for the tooltip
const tooltipStyles: React.CSSProperties = {
  borderRadius: 'var(--radius)',
  border: '1px solid hsl(var(--border))',
  boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)',
  padding: '16px',
  maxWidth: '360px',
  backgroundColor: 'hsl(var(--card))',
  color: 'hsl(var(--card-foreground))',
}

const tooltipTitleStyles: React.CSSProperties = {
  fontSize: '15px',
  fontWeight: '600',
  marginBottom: '8px',
  color: 'hsl(var(--foreground))',
}

const tooltipContentStyles: React.CSSProperties = {
  fontSize: '14px',
  lineHeight: '1.5',
  color: 'hsl(var(--muted-foreground))',
}

const tooltipFooterStyles: React.CSSProperties = {
  marginTop: '16px',
  padding: '0',
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
}

function getTourConfig(tourId: OnboardingTourId) {
  switch (tourId) {
    case 'platform':
      return platformTourConfig
    default:
      return null
  }
}

export function OnboardingTour({ tourId }: OnboardingTourProps) {
  const t = useTranslations()
  const router = useRouter()
  const pathname = usePathname()
  const { state, nextStep, prevStep, completeTour } = useOnboarding()
  const [isNavigating, setIsNavigating] = React.useState(false)
  const controlsRef = React.useRef<Controls | null>(null)

  const config = getTourConfig(tourId)

  // Get steps filtered by current route for platform tour
  const steps = React.useMemo(() => {
    if (!config) return []
    if (tourId === 'platform') {
      return getPlatformStepsForRoute(pathname)
    }
    return config.steps
  }, [config, tourId, pathname])

  // Calculate the effective step index based on route filtering
  const effectiveStepIndex = React.useMemo(() => {
    if (tourId !== 'platform') return state.currentStep

    // For platform tour, map global step index to filtered step index
    const allSteps = config?.steps || []
    const currentGlobalStep = allSteps[state.currentStep]
    if (!currentGlobalStep) return 0

    const filteredIndex = steps.findIndex(s => s.target === currentGlobalStep.target)
    return filteredIndex >= 0 ? filteredIndex : 0
  }, [tourId, state.currentStep, config, steps])

  const handleJoyrideEvent = React.useCallback(
    (data: EventData, controls: Controls) => {
      const { action, index, type } = data

      // Store controls reference
      controlsRef.current = controls

      if (type === EVENTS.STEP_AFTER || type === EVENTS.TARGET_NOT_FOUND) {
        // Handle navigation for steps that require route changes
        const currentStep = steps[index]
        if (currentStep?.route && action === ACTIONS.NEXT) {
          setIsNavigating(true)
          router.push(currentStep.route)
          // Wait for navigation to complete
          setTimeout(() => {
            setIsNavigating(false)
            nextStep()
          }, 500)
          return
        }

        if (action === ACTIONS.NEXT) {
          nextStep()
        } else if (action === ACTIONS.PREV) {
          prevStep()
        }
      }

      if (data.status === STATUS.FINISHED || data.status === STATUS.SKIPPED) {
        completeTour(tourId)
      }
    },
    [steps, router, nextStep, prevStep, completeTour, tourId]
  )

  const handleNext = React.useCallback(() => {
    const currentStepData = steps[effectiveStepIndex]
    if (currentStepData?.route && pathname !== currentStepData.route) {
      setIsNavigating(true)
      router.push(currentStepData.route)
      setTimeout(() => {
        setIsNavigating(false)
        nextStep()
      }, 500)
    } else if (effectiveStepIndex < steps.length - 1) {
      nextStep()
    } else {
      completeTour(tourId)
    }
  }, [steps, effectiveStepIndex, pathname, router, nextStep, completeTour, tourId])

  const handleBack = React.useCallback(() => {
    prevStep()
  }, [prevStep])

  const handleSkip = React.useCallback(() => {
    completeTour(tourId)
  }, [completeTour, tourId])

  if (!config || state.currentTour !== tourId || !state.isRunning || isNavigating) {
    return null
  }

  if (steps.length === 0) {
    return null
  }

  const isFirstStep = effectiveStepIndex === 0

  return (
    <Joyride
      steps={steps}
      stepIndex={effectiveStepIndex}
      run={state.isRunning && state.currentTour === tourId}
      continuous
      options={{
        showProgress: true,
        skipBeacon: true,
        overlayClickAction: 'close',
        dismissKeyAction: false,
        primaryColor: 'hsl(var(--primary))',
        backgroundColor: 'hsl(var(--card))',
        textColor: 'hsl(var(--card-foreground))',
        overlayColor: 'hsl(var(--background) / 0.8)',
        arrowColor: 'hsl(var(--card))',
        zIndex: 10000,
      }}
      onEvent={handleJoyrideEvent}
      tooltipComponent={({
        index,
        isLastStep: tooltipIsLastStep,
        step,
        size,
      }) => (
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
              {!isFirstStep && (
                <Button variant="ghost" size="sm" onClick={handleBack}>
                  {t('platform.onboarding.back')}
                </Button>
              )}
              <Button variant="ghost" size="sm" onClick={handleSkip}>
                {t('platform.onboarding.skip')}
              </Button>
              <Button size="sm" onClick={handleNext}>
                {tooltipIsLastStep
                  ? t('platform.onboarding.finish')
                  : t('platform.onboarding.next')}
              </Button>
            </div>
          </div>
        </div>
      )}
    />
  )
}
