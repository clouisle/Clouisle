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

  const handleJoyrideEvent = React.useCallback(
    (data: EventData, controls: Controls) => {
      const { action, type } = data

      // Store controls reference
      controlsRef.current = controls

      if (type === EVENTS.STEP_AFTER || type === EVENTS.TARGET_NOT_FOUND) {
        // Only handle NEXT action from Joyride
        // PREV is handled by our custom back button
        if (action === ACTIONS.NEXT) {
          // Check if next step requires navigation
          const nextStepIndex = currentStepIndex + 1
          const nextStepData = steps[nextStepIndex]

          if (nextStepData?.route) {
            const isOnCorrectRoute = pathname === nextStepData.route ||
              pathname.startsWith(nextStepData.route + '/')
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

      if (data.status === STATUS.FINISHED || data.status === STATUS.SKIPPED) {
        completeTour(tourId)
      }
    },
    [steps, currentStepIndex, pathname, router, nextStep, completeTour, tourId]
  )

  // Handle navigation when step changes and requires a different route
  React.useEffect(() => {
    if (!currentStep?.route) return

    // Check if we need to navigate to the step's route
    // Use exact matching to avoid /app matching /app/models
    const isOnCorrectRoute = pathname === currentStep.route ||
      pathname.startsWith(currentStep.route + '/')
    if (!isOnCorrectRoute) {
      router.push(currentStep.route)
    }
  }, [currentStep, pathname, router])

  const handleNext = React.useCallback(() => {
    if (currentStepIndex < steps.length - 1) {
      nextStep()
    } else {
      completeTour(tourId)
    }
  }, [currentStepIndex, steps.length, nextStep, completeTour, tourId])

  const handleBack = React.useCallback(() => {
    prevStep()
  }, [prevStep])

  const handleSkip = React.useCallback(() => {
    completeTour(tourId)
  }, [completeTour, tourId])

  if (!config || state.currentTour !== tourId || !state.isRunning) {
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
