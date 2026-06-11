import type { OnboardingStep, OnboardingTourConfig } from './types'

const platformSteps: OnboardingStep[] = [
  // P1: Home page overview
  {
    target: '[data-testid="platform-header-nav"]',
    content: 'onboarding.step1.description',
    title: 'onboarding.step1.title',
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
    target: '[data-testid="platform-home-quick-actions"]',
    content: 'onboarding.step3.description',
    title: 'onboarding.step3.title',
    placement: 'auto',
    route: '/app',
  },

  // P2: Model configuration
  {
    target: '[data-testid="nav-models"]',
    content: 'onboarding.step4.description',
    title: 'onboarding.step4.title',
    placement: 'auto',
    route: '/app/models',
  },
  {
    target: '[data-testid="models-grid"]',
    content: 'onboarding.step5.description',
    title: 'onboarding.step5.title',
    placement: 'auto',
    route: '/app/models',
  },

  // P3: Knowledge base
  {
    target: '[data-testid="nav-kb"]',
    content: 'onboarding.step6.description',
    title: 'onboarding.step6.title',
    placement: 'auto',
    route: '/app/kb',
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

  // P4: Create Agent
  {
    target: '[data-testid="nav-apps"]',
    content: 'onboarding.step8.description',
    title: 'onboarding.step8.title',
    placement: 'auto',
    route: '/app/apps',
  },
  {
    target: '[data-testid="apps-create-button"]',
    content: 'onboarding.step9.description',
    title: 'onboarding.step9.title',
    placement: 'auto',
    route: '/app/apps',
  },

  // P5: Chat
  {
    target: '[data-testid="chat-input"]',
    content: 'onboarding.step10.description',
    title: 'onboarding.step10.title',
    placement: 'auto',
    route: '/chat',
  },
]

export const platformTourConfig: OnboardingTourConfig = {
  id: 'platform',
  title: 'onboarding.tourTitle',
  description: 'onboarding.tourDescription',
  steps: platformSteps,
  autoStart: true,
}

export function getPlatformStepsForRoute(pathname: string): OnboardingStep[] {
  // Return only steps relevant to the current route
  return platformSteps.filter(step => {
    if (!step.route) return true // Steps without route are shown on any page
    return pathname.startsWith(step.route)
  })
}
