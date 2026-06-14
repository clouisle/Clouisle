import type { OnboardingStep, OnboardingTourConfig } from './types'

const capabilitiesTourSteps: OnboardingStep[] = [
  // ========== Tabs (Tools vs Skills) ==========
  {
    target: '[data-testid="capabilities-tabs"]',
    content: 'onboarding.step21.description',
    title: 'onboarding.step21.title',
    placement: 'bottom',
  },
  // ========== Tools List Overview ==========
  {
    target: '[data-testid="capabilities-tools-panel"]',
    content: 'onboarding.step22.description',
    title: 'onboarding.step22.title',
    placement: 'auto',
  },
  // ========== Tools Tab - Create Tool Button ==========
  {
    target: '[data-testid="capabilities-create-tool-button"]',
    content: 'onboarding.step23.description',
    title: 'onboarding.step23.title',
    placement: 'bottom',
    advanceOnClick: true,
    overlayClickAction: false,
  },
  // ========== Tools Tab - Create Menu Dropdown ==========
  {
    target: '[data-testid="capabilities-create-tool-menu"]',
    content: 'onboarding.step24.description',
    title: 'onboarding.step24.title',
    placement: 'bottom',
    overlayClickAction: false,
  },
  // ========== Tools Tab - Import Button ==========
  {
    target: '[data-testid="capabilities-import-button"]',
    content: 'onboarding.step25.description',
    title: 'onboarding.step25.title',
    placement: 'bottom',
    overlayClickAction: false,
  },
  // ========== Tools Tab - Refresh Button ==========
  {
    target: '[data-testid="capabilities-refresh-button"]',
    content: 'onboarding.step26.description',
    title: 'onboarding.step26.title',
    placement: 'bottom',
    overlayClickAction: false,
  },
  // ========== Switch to Skills Tab ==========
  {
    target: '[data-testid="capabilities-skills-tab"]',
    content: 'onboarding.step27.description',
    title: 'onboarding.step27.title',
    placement: 'bottom',
    advanceOnClick: true,
    overlayClickAction: false,
  },
  // ========== Skills Tab - Import Button ==========
  {
    target: '[data-testid="skills-import-button"]',
    content: 'onboarding.step28.description',
    title: 'onboarding.step28.title',
    placement: 'bottom',
    overlayClickAction: false,
  },
  // ========== Skills Tab - Refresh Button ==========
  {
    target: '[data-testid="skills-refresh-button"]',
    content: 'onboarding.step29.description',
    title: 'onboarding.step29.title',
    placement: 'bottom',
    overlayClickAction: false,
  },
]

export const capabilitiesTourConfig: OnboardingTourConfig = {
  id: 'capabilities',
  title: 'onboarding.tourCapabilitiesTitle',
  description: 'onboarding.tourCapabilitiesDescription',
  steps: capabilitiesTourSteps,
  autoStart: false,
}
