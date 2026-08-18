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
    advanceOnClick: true,
    overlayClickAction: false,
  },
  {
    target: '[data-testid="api-key-dialog"]',
    content: 'onboarding.step32c.description',
    title: 'onboarding.step32c.title',
    // Dialog target: bottom keeps the tooltip below the dialog so the form
    // stays visible and fillable (same pattern as the KB dialog steps).
    placement: 'bottom',
    route: '/app/api-keys',
    overlayClickAction: false,
  },
  // ========== Key Shown Only Once ==========
  {
    target: '[data-testid="show-key-dialog"]',
    content: 'onboarding.step32d.description',
    title: 'onboarding.step32d.title',
    placement: 'bottom',
    route: '/app/api-keys',
    overlayClickAction: false,
  },
  {
    target: '[data-testid="show-key-copy-button"]',
    content: 'onboarding.step32e.description',
    title: 'onboarding.step32e.title',
    placement: 'left',
    route: '/app/api-keys',
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
