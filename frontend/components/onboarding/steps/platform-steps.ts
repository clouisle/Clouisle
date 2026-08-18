import type { OnboardingTourConfig, OnboardingTourId } from './types'
import { overviewTourConfig } from './overview-steps'
import { modelsTourConfig } from './models-steps'
import { kbTourConfig } from './kb-steps'
import { appCreateTourConfig } from './app-create-steps'
import { appConfigTourConfig } from './app-config-steps'
import { workflowConfigTourConfig } from './workflow-steps'
import { capabilitiesTourConfig } from './capabilities-steps'
import { adminModelSetupTourConfig } from './admin-models-steps'
import { apiKeysTourConfig } from './api-keys-steps'

// Export individual tour configs
export {
  overviewTourConfig,
  modelsTourConfig,
  kbTourConfig,
  appCreateTourConfig,
  appConfigTourConfig,
  workflowConfigTourConfig,
  capabilitiesTourConfig,
  adminModelSetupTourConfig,
  apiKeysTourConfig,
}

// Array of all tour configs for easy iteration
export const allTourConfigs: OnboardingTourConfig[] = [
  overviewTourConfig,
  modelsTourConfig,
  kbTourConfig,
  appCreateTourConfig,
  appConfigTourConfig,
  apiKeysTourConfig,
  workflowConfigTourConfig,
  capabilitiesTourConfig,
  adminModelSetupTourConfig,
]

// Get tour config by ID
export function getTourConfigById(id: string): OnboardingTourConfig | undefined {
  return allTourConfigs.find(config => config.id === id)
}

// The tour that follows the given tour in the prerequisite chain
export function getNextTourInChain(tourId: OnboardingTourId): OnboardingTourId | null {
  return allTourConfigs.find(config => config.prerequisites?.includes(tourId))?.id ?? null
}

// Get the first auto-start tour
export function getAutoStartTour(): string | null {
  const autoStartTour = allTourConfigs.find(config => config.autoStart)
  return autoStartTour?.id || null
}
