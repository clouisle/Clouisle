import type { OnboardingStep, OnboardingTourConfig } from './types'

const apiKeysSteps: OnboardingStep[] = [
  // ========== Page Overview ==========
  {
    target: '[data-testid="api-keys-page"]',
    content: 'onboarding.step32a.description',
    title: 'onboarding.step32a.title',
    // Full-viewport target: center keeps the tooltip in view, like the
    // kb-detail-page step.
    placement: 'center',
    route: '/app/api-keys',
  },
  // ========== Create a Key ==========
  {
    target: '[data-testid="api-keys-create-button"]',
    content: 'onboarding.step32b.description',
    title: 'onboarding.step32b.title',
    placement: 'bottom',
    route: '/app/api-keys',
    // Clicking create hands off to the real create flow: the full key is
    // shown only once in the follow-up dialog, which is exactly the teaching.
    advanceOnClick: true,
    overlayClickAction: false,
  },
]

export const apiKeysTourConfig: OnboardingTourConfig = {
  id: 'apiKeys',
  title: 'onboarding.tourApiKeysTitle',
  description: 'onboarding.tourApiKeysDescription',
  steps: apiKeysSteps,
  autoStart: false,
}
