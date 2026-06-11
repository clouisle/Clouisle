import type { OnboardingStep, OnboardingTourConfig } from './types'

const platformSteps: OnboardingStep[] = [
  // P1: Home page overview
  {
    target: '[data-testid="platform-header-nav"]',
    content: 'platform.onboarding.step1.description',
    title: 'platform.onboarding.step1.title',
    placement: 'bottom',
  },
  {
    target: '[data-testid="platform-home-stat-cards"]',
    content: 'platform.onboarding.step2.description',
    title: 'platform.onboarding.step2.title',
    placement: 'bottom',
  },
  {
    target: '[data-testid="platform-home-quick-actions"]',
    content: 'platform.onboarding.step3.description',
    title: 'platform.onboarding.step3.title',
    placement: 'left',
  },

  // P2: Model configuration
  {
    target: '[data-testid="nav-models"]',
    content: 'platform.onboarding.step4.description',
    title: 'platform.onboarding.step4.title',
    placement: 'bottom-end',
    route: '/app/models',
  },
  {
    target: '[data-testid="models-grid"]',
    content: 'platform.onboarding.step5.description',
    title: 'platform.onboarding.step5.title',
    placement: 'top',
    route: '/app/models',
  },

  // P3: Knowledge base
  {
    target: '[data-testid="nav-kb"]',
    content: 'platform.onboarding.step6.description',
    title: 'platform.onboarding.step6.title',
    placement: 'bottom-end',
    route: '/app/kb',
  },
  {
    target: '[data-testid="kb-create-card"]',
    content: 'platform.onboarding.step7.description',
    title: 'platform.onboarding.step7.title',
    placement: 'right',
    route: '/app/kb',
  },

  // P4: Create Agent
  {
    target: '[data-testid="nav-apps"]',
    content: 'platform.onboarding.step8.description',
    title: 'platform.onboarding.step8.title',
    placement: 'bottom-end',
    route: '/app/apps',
  },
  {
    target: '[data-testid="apps-create-button"]',
    content: 'platform.onboarding.step9.description',
    title: 'platform.onboarding.step9.title',
    placement: 'bottom-end',
    route: '/app/apps',
  },

  // P5: Chat
  {
    target: '[data-testid="chat-input"]',
    content: 'platform.onboarding.step10.description',
    title: 'platform.onboarding.step10.title',
    placement: 'top',
    route: '/chat',
  },
]

export const platformTourConfig: OnboardingTourConfig = {
  id: 'platform',
  title: 'platform.onboarding.tourTitle',
  description: 'platform.onboarding.tourDescription',
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
