'use client'

import * as React from 'react'

export type OnboardingTourId = 'platform' | 'dashboard'

interface OnboardingState {
  completedTours: OnboardingTourId[]
  currentTour: OnboardingTourId | null
  currentStep: number
  isRunning: boolean
}

interface OnboardingContextType {
  state: OnboardingState
  startTour: (tourId: OnboardingTourId) => void
  stopTour: () => void
  nextStep: () => void
  prevStep: () => void
  goToStep: (step: number) => void
  completeTour: (tourId: OnboardingTourId) => void
  resetTour: (tourId: OnboardingTourId) => void
  resetAllTours: () => void
  isTourCompleted: (tourId: OnboardingTourId) => boolean
}

const STORAGE_KEY = 'clouisle-onboarding-state'

const OnboardingContext = React.createContext<OnboardingContextType | undefined>(undefined)

function loadState(): OnboardingState {
  if (typeof window === 'undefined') {
    return { completedTours: [], currentTour: null, currentStep: 0, isRunning: false }
  }

  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) {
      const parsed = JSON.parse(saved)
      return {
        completedTours: parsed.completedTours || [],
        currentTour: null,
        currentStep: 0,
        isRunning: false,
      }
    }
  } catch {
    // Ignore parse errors
  }

  return { completedTours: [], currentTour: null, currentStep: 0, isRunning: false }
}

function saveState(state: OnboardingState) {
  if (typeof window === 'undefined') return

  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        completedTours: state.completedTours,
      })
    )
  } catch {
    // Ignore storage errors
  }
}

export function OnboardingProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = React.useState<OnboardingState>(loadState)

  // Persist completed tours to localStorage
  React.useEffect(() => {
    saveState(state)
  }, [state])

  const startTour = React.useCallback((tourId: OnboardingTourId) => {
    setState(prev => ({
      ...prev,
      currentTour: tourId,
      currentStep: 0,
      isRunning: true,
    }))
  }, [])

  const stopTour = React.useCallback(() => {
    setState(prev => ({
      ...prev,
      currentTour: null,
      currentStep: 0,
      isRunning: false,
    }))
  }, [])

  const nextStep = React.useCallback(() => {
    setState(prev => ({
      ...prev,
      currentStep: prev.currentStep + 1,
    }))
  }, [])

  const prevStep = React.useCallback(() => {
    setState(prev => ({
      ...prev,
      currentStep: Math.max(0, prev.currentStep - 1),
    }))
  }, [])

  const goToStep = React.useCallback((step: number) => {
    setState(prev => ({
      ...prev,
      currentStep: step,
    }))
  }, [])

  const completeTour = React.useCallback((tourId: OnboardingTourId) => {
    setState(prev => ({
      ...prev,
      completedTours: prev.completedTours.includes(tourId)
        ? prev.completedTours
        : [...prev.completedTours, tourId],
      currentTour: null,
      currentStep: 0,
      isRunning: false,
    }))
  }, [])

  const resetTour = React.useCallback((tourId: OnboardingTourId) => {
    setState(prev => ({
      ...prev,
      completedTours: prev.completedTours.filter(id => id !== tourId),
    }))
  }, [])

  const resetAllTours = React.useCallback(() => {
    setState({
      completedTours: [],
      currentTour: null,
      currentStep: 0,
      isRunning: false,
    })
  }, [])

  const isTourCompleted = React.useCallback(
    (tourId: OnboardingTourId) => {
      return state.completedTours.includes(tourId)
    },
    [state.completedTours]
  )

  const value = React.useMemo(
    () => ({
      state,
      startTour,
      stopTour,
      nextStep,
      prevStep,
      goToStep,
      completeTour,
      resetTour,
      resetAllTours,
      isTourCompleted,
    }),
    [
      state,
      startTour,
      stopTour,
      nextStep,
      prevStep,
      goToStep,
      completeTour,
      resetTour,
      resetAllTours,
      isTourCompleted,
    ]
  )

  return (
    <OnboardingContext.Provider value={value}>
      {children}
    </OnboardingContext.Provider>
  )
}

export function useOnboarding() {
  const context = React.useContext(OnboardingContext)
  if (context === undefined) {
    throw new Error('useOnboarding must be used within an OnboardingProvider')
  }
  return context
}

export function useOptionalOnboarding() {
  return React.useContext(OnboardingContext)
}
