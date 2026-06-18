import type { OnboardingTourConfig } from './types'
import { overviewTourConfig } from './overview-steps'
import { modelsTourConfig } from './models-steps'
import { kbTourConfig } from './kb-steps'
import { appCreateTourConfig } from './app-create-steps'
import { appConfigTourConfig } from './app-config-steps'
import { capabilitiesTourConfig } from './capabilities-steps'

// Export individual tour configs
export {
  overviewTourConfig,
  modelsTourConfig,
  kbTourConfig,
  appCreateTourConfig,
  appConfigTourConfig,
  capabilitiesTourConfig,
}

// Array of all tour configs for easy iteration
export const allTourConfigs: OnboardingTourConfig[] = [
  overviewTourConfig,
  modelsTourConfig,
  kbTourConfig,
  appCreateTourConfig,
  appConfigTourConfig,
  capabilitiesTourConfig,
]

// Get tour config by ID
export function getTourConfigById(id: string): OnboardingTourConfig | undefined {
  return allTourConfigs.find(config => config.id === id)
}

// Get the first auto-start tour
export function getAutoStartTour(): string | null {
  const autoStartTour = allTourConfigs.find(config => config.autoStart)
  return autoStartTour?.id || null
}
