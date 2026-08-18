import type { OnboardingStep, OnboardingTourConfig } from './types'

const apiKeysSteps: OnboardingStep[] = [
  // ========== Page Overview ==========
  {
    target: '[data-testid="api-keys-page"]',
    content: 'onboarding.step32a.description',
    title: 'onboarding.step32a.title',
    placement: 'center',
    route: '/app/api-keys',
    targetWaitTimeout: 5000,
  },
  // ========== Open the Create Dialog ==========
  {
    target: '[data-testid="api-keys-create-button"]',
    content: 'onboarding.step32b.description',
    title: 'onboarding.step32b.title',
    placement: 'bottom',
    route: '/app/api-keys',
    advanceOnClick: true,
    overlayClickAction: false,
    targetWaitTimeout: 5000,
  },
  // ========== Complete the Create Dialog ==========
  {
    target: '[data-testid="api-key-name-input"]',
    content: 'onboarding.step32c.description',
    title: 'onboarding.step32c.title',
    placement: 'bottom',
    route: '/app/api-keys',
    overlayClickAction: false,
    targetWaitTimeout: 5000,
  },
  // ========== Configure Access ==========
  {
    target: '[data-testid="api-key-allowed-agents"]',
    content: 'onboarding.step32d.description',
    title: 'onboarding.step32d.title',
    placement: 'left',
    route: '/app/api-keys',
    overlayClickAction: false,
    targetWaitTimeout: 5000,
  },
  {
    target: '[data-testid="api-key-allowed-workflows"]',
    content: 'onboarding.step32e.description',
    title: 'onboarding.step32e.title',
    placement: 'right',
    route: '/app/api-keys',
    overlayClickAction: false,
    targetWaitTimeout: 5000,
  },
  {
    target: '[data-testid="api-key-submit"]',
    content: 'onboarding.step32f.description',
    title: 'onboarding.step32f.title',
    placement: 'top',
    route: '/app/api-keys',
    advanceOnSuccess: true,
    overlayClickAction: false,
    targetWaitTimeout: 5000,
  },
]

export const apiKeysTourConfig: OnboardingTourConfig = {
  id: 'apiKeys',
  title: 'onboarding.tourApiKeysTitle',
  description: 'onboarding.tourApiKeysDescription',
  steps: apiKeysSteps,
  autoStart: false,
}
