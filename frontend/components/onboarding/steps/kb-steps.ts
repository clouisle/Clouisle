import type { OnboardingStep, OnboardingTourConfig } from './types'

const kbSteps: OnboardingStep[] = [
  // Knowledge base
  {
    target: '[data-testid="nav-kb"]',
    content: 'onboarding.step6.description',
    title: 'onboarding.step6.title',
    placement: 'auto',
    route: '/app/kb',
    advanceOnClick: true,
    waitForRouteChange: true,
  },
  {
    target: '[data-testid="kb-create-card"]',
    content: 'onboarding.step7.description',
    title: 'onboarding.step7.title',
    placement: 'auto',
    route: '/app/kb',
  },
  {
    target: '[data-testid="kb-import-button"]',
    content: 'onboarding.step7b.description',
    title: 'onboarding.step7b.title',
    placement: 'auto',
    route: '/app/kb',
  },
]

export const kbTourConfig: OnboardingTourConfig = {
  id: 'kb',
  title: 'onboarding.tourKBTitle',
  description: 'onboarding.tourKBDescription',
  steps: kbSteps,
  autoStart: false,
}
