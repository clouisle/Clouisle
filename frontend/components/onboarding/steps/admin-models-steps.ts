import type { OnboardingStep, OnboardingTourConfig } from './types'

const adminModelSetupSteps: OnboardingStep[] = [
  {
    target: '[data-testid="admin-models-list"]',
    content: 'onboarding.step30a.description',
    title: 'onboarding.step30a.title',
    placement: 'auto',
    route: '/models',
  },
  {
    target: '[data-testid="admin-models-create-button"]',
    content: 'onboarding.step30b.description',
    title: 'onboarding.step30b.title',
    placement: 'left',
    route: '/models',
    advanceOnClick: true,
    overlayClickAction: false,
  },
  {
    target: '[data-testid="admin-model-dialog-provider-selection"]',
    content: 'onboarding.step30c.description',
    title: 'onboarding.step30c.title',
    placement: 'bottom',
    route: '/models',
    overlayClickAction: false,
  },
  {
    target: '[data-testid="admin-model-dialog-api-config"]',
    content: 'onboarding.step30d.description',
    title: 'onboarding.step30d.title',
    placement: 'bottom',
    route: '/models',
    overlayClickAction: false,
  },
  {
    target: '[data-testid="admin-model-dialog-model-id"]',
    content: 'onboarding.step30e.description',
    title: 'onboarding.step30e.title',
    placement: 'bottom',
    route: '/models',
    overlayClickAction: false,
  },
  {
    target: '[data-testid="admin-model-dialog-test-connection"]',
    content: 'onboarding.step30f.description',
    title: 'onboarding.step30f.title',
    placement: 'top',
    route: '/models',
    overlayClickAction: false,
  },
  {
    target: '[data-testid="admin-model-dialog-enabled"]',
    content: 'onboarding.step30g.description',
    title: 'onboarding.step30g.title',
    placement: 'left',
    route: '/models',
    overlayClickAction: false,
  },
]

export const adminModelSetupTourConfig: OnboardingTourConfig = {
  id: 'adminModelSetup',
  title: 'onboarding.tourAdminModelSetupTitle',
  description: 'onboarding.tourAdminModelSetupDescription',
  steps: adminModelSetupSteps,
  autoStart: false,
  showInPlatformMenu: false,
}
