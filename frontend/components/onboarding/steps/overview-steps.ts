import type { OnboardingStep, OnboardingTourConfig } from './types'

const overviewSteps: OnboardingStep[] = [
  // Home page overview
  {
    target: '[data-testid="platform-header-nav"]',
    content: 'onboarding.step1.description',
    title: 'onboarding.step1.title',
    placement: 'auto',
    route: '/app',
  },
  {
    target: '[data-testid="platform-home-header"]',
    content: 'onboarding.step1b.description',
    title: 'onboarding.step1b.title',
    placement: 'auto',
    route: '/app',
  },
  {
    target: '[data-testid="platform-home-stat-cards"]',
    content: 'onboarding.step2.description',
    title: 'onboarding.step2.title',
    placement: 'auto',
    route: '/app',
  },
  {
    target: '[data-testid="platform-home-usage-trend"]',
    content: 'onboarding.step2b.description',
    title: 'onboarding.step2b.title',
    placement: 'auto',
    route: '/app',
  },
  {
    target: '[data-testid="platform-home-resource-overview"]',
    content: 'onboarding.step2c.description',
    title: 'onboarding.step2c.title',
    placement: 'auto',
    route: '/app',
  },
  {
    target: '[data-testid="platform-home-quick-actions"]',
    content: 'onboarding.step3.description',
    title: 'onboarding.step3.title',
    placement: 'auto',
    route: '/app',
  },
  {
    target: '[data-testid="platform-home-recent-items"]',
    content: 'onboarding.step3b.description',
    title: 'onboarding.step3b.title',
    placement: 'auto',
    route: '/app',
  },
]

export const overviewTourConfig: OnboardingTourConfig = {
  id: 'overview',
  title: 'onboarding.tourOverviewTitle',
  description: 'onboarding.tourOverviewDescription',
  steps: overviewSteps,
  autoStart: true,
}
