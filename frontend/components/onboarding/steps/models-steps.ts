import type { OnboardingStep, OnboardingTourConfig } from './types'

const modelsSteps: OnboardingStep[] = [
  // Model configuration
  {
    target: '[data-testid="nav-models"]',
    content: 'onboarding.step4.description',
    title: 'onboarding.step4.title',
    placement: 'auto',
    route: '/app/models',
    advanceOnClick: true,
    waitForRouteChange: true,
  },
  {
    target: '[data-testid="models-grid"]',
    content: 'onboarding.step5.description',
    title: 'onboarding.step5.title',
    placement: 'auto',
    route: '/app/models',
  },
]

export const modelsTourConfig: OnboardingTourConfig = {
  id: 'models',
  title: 'onboarding.tourModelsTitle',
  description: 'onboarding.tourModelsDescription',
  steps: modelsSteps,
  autoStart: false,
}
