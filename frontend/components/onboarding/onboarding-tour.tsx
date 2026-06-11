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
import { platformTourConfig } from './steps/platform-steps'

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
  const { state, startTour, nextStep, prevStep, completeTour } = useOnboarding()
  const [isNavigating, setIsNavigating] = React.useState(false)
  const controlsRef = React.useRef<Controls | null>(null)
  const hasAutoStarted = React.useRef(false)

  const config = getTourConfig(tourId)

  // Auto-start tour for new users on the home page
  React.useEffect(() => {
    if (
      tourId === 'platform' &&
      config?.autoStart &&
      !state.isRunning &&
      !state.completedTours.includes('platform') &&
      pathname === '/app' &&
      !hasAutoStarted.current
    ) {
      hasAutoStarted.current = true
      // Small delay to ensure the page is fully loaded
      const timer = setTimeout(() => {
        startTour('platform')
      }, 500)
      return () => clearTimeout(timer)
    }
  }, [tourId, config, state.isRunning, state.completedTours, pathname, startTour])

  // Get all steps (no filtering by route)
  const steps = React.useMemo(() => {
    if (!config) return []
    return config.steps
  }, [config])

  // Current step index
  const currentStepIndex = state.currentStep

  // Get current step data
  const currentStep = steps[currentStepIndex]

  // Handle navigation when step has a route
  React.useEffect(() => {
    if (!currentStep?.route || isNavigating) return

    // Check if we need to navigate
    const needsNavigation = !pathname.startsWith(currentStep.route)
    if (needsNavigation) {
      setIsNavigating(true)
      router.push(currentStep.route)
      // Wait for navigation to complete
      const timer = setTimeout(() => {
        setIsNavigating(false)
      }, 500)
      return () => clearTimeout(timer)
    }
  }, [currentStep, pathname, router, isNavigating])

  const handleJoyrideEvent = React.useCallback(
    (data: EventData, controls: Controls) => {
      const { action, type } = data

      // Store controls reference
      controlsRef.current = controls

      if (type === EVENTS.STEP_AFTER || type === EVENTS.TARGET_NOT_FOUND) {
        if (action === ACTIONS.NEXT) {
          // Check if next step requires navigation
          const nextStepIndex = currentStepIndex + 1
          const nextStepData = steps[nextStepIndex]

          if (nextStepData?.route && !pathname.startsWith(nextStepData.route)) {
            // Navigate first, then advance step
            setIsNavigating(true)
            router.push(nextStepData.route)
            setTimeout(() => {
              setIsNavigating(false)
              nextStep()
            }, 500)
          } else {
            nextStep()
          }
        } else if (action === ACTIONS.PREV) {
          prevStep()
        }
      }

      if (data.status === STATUS.FINISHED || data.status === STATUS.SKIPPED) {
        completeTour(tourId)
      }
    },
    [steps, currentStepIndex, pathname, router, nextStep, prevStep, completeTour, tourId]
  )

  const handleNext = React.useCallback(() => {
    const nextStepIndex = currentStepIndex + 1
    const nextStepData = steps[nextStepIndex]

    if (nextStepData?.route && !pathname.startsWith(nextStepData.route)) {
      // Navigate first, then advance step
      setIsNavigating(true)
      router.push(nextStepData.route)
      setTimeout(() => {
        setIsNavigating(false)
        nextStep()
      }, 500)
    } else if (currentStepIndex < steps.length - 1) {
      nextStep()
    } else {
      completeTour(tourId)
    }
  }, [steps, currentStepIndex, pathname, router, nextStep, completeTour, tourId])

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

  const isFirstStep = currentStepIndex === 0

  return (
    <Joyride
      steps={steps}
      stepIndex={currentStepIndex}
      run={state.isRunning && state.currentTour === tourId}
      continuous
      scrollToFirstStep
      scrollOffset={100}
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
        scrollOffset: 100,
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
                  {t('onboarding.back')}
                </Button>
              )}
              <Button variant="ghost" size="sm" onClick={handleSkip}>
                {t('onboarding.skip')}
              </Button>
              <Button size="sm" onClick={handleNext}>
                {tooltipIsLastStep
                  ? t('onboarding.finish')
                  : t('onboarding.next')}
              </Button>
            </div>
          </div>
        </div>
      )}
    />
  )
}
