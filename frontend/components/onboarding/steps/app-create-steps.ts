import type { OnboardingStep, OnboardingTourConfig } from './types'

const appCreateSteps: OnboardingStep[] = [
  // ========== Navigate to Apps ==========
  {
    target: '[data-testid="nav-apps"]',
    content: 'onboarding.step8.description',
    title: 'onboarding.step8.title',
    placement: 'auto',
    route: '/app/apps',
    advanceOnClick: true,
    waitForRouteChange: true,
  },
  // ========== Create Agent Dialog ==========
  {
    target: '[data-testid="apps-create-button"]',
    content: 'onboarding.step9.description',
    title: 'onboarding.step9.title',
    placement: 'auto',
    route: '/app/apps',
    advanceOnClick: true,
    overlayClickAction: false,
  },
  {
    target: '[data-testid="app-create-type-selector"]',
    content: 'onboarding.step9b.description',
    title: 'onboarding.step9b.title',
    placement: 'auto',
    route: '/app/apps',
    advanceOnClick: true,
    overlayClickAction: false,
  },
  {
    target: '[data-testid="app-create-name-input"]',
    content: 'onboarding.step9c.description',
    title: 'onboarding.step9c.title',
    placement: 'auto',
    route: '/app/apps',
    overlayClickAction: false,
  },
  {
    target: '[data-testid="app-create-description-input"]',
    content: 'onboarding.step9d.description',
    title: 'onboarding.step9d.title',
    placement: 'auto',
    route: '/app/apps',
    overlayClickAction: false,
  },
  {
    target: '[data-testid="app-create-submit"]',
    content: 'onboarding.step9e.description',
    title: 'onboarding.step9e.title',
    placement: 'auto',
    route: '/app/apps',
    advanceOnClick: true,
    waitForRouteChange: true,
    overlayClickAction: false,
  },
  // ========== Agent Card Introduction ==========
  {
    target: '[data-testid^="app-card-"]:first-of-type',
    content: 'onboarding.step17.description',
    title: 'onboarding.step17.title',
    placement: 'right',
    delay: 500,
    overlayClickAction: false,
  },
  {
    target: '[data-testid^="app-actions-button-"]:first-of-type',
    content: 'onboarding.step17a.description',
    title: 'onboarding.step17a.title',
    placement: 'left',
    advanceOnClick: true,
    overlayClickAction: false,
  },
  {
    target: '[data-testid^="app-chat-button-"]:first-of-type',
    content: 'onboarding.step17b.description',
    title: 'onboarding.step17b.title',
    placement: 'left',
    advanceOnClick: true,
    overlayClickAction: false,
  },
]

export const appCreateTourConfig: OnboardingTourConfig = {
  id: 'appCreate',
  title: 'onboarding.tourAppCreateTitle',
  description: 'onboarding.tourAppCreateDescription',
  steps: appCreateSteps,
  autoStart: false,
}
