import { describe, expect, test } from 'bun:test'

import {
  allTourConfigs,
  getAutoStartTour,
  getTourConfigById,
} from './platform-steps'

describe('onboarding tour configurations', () => {
  test('registers every tour once with usable ordered steps', () => {
    expect(allTourConfigs.map(config => config.id)).toEqual([
      'overview',
      'models',
      'kb',
      'appCreate',
      'appConfig',
      'capabilities',
    ])

    for (const config of allTourConfigs) {
      expect(config.title).toStartWith('onboarding.')
      expect(config.description).toStartWith('onboarding.')
      expect(config.steps.length).toBeGreaterThan(0)

      for (const step of config.steps) {
        expect(step.target).toBeTruthy()
        expect(step.title).toStartWith('onboarding.')
        expect(step.content).toStartWith('onboarding.')
      }
    }
  })

  test('uses selectors from the current pages', () => {
    const appConfigTargets = getTourConfigById('appConfig')?.steps.map(step => step.target) ?? []
    const knowledgeBaseTargets = getTourConfigById('kb')?.steps.map(step => step.target) ?? []

    expect(appConfigTargets).toContain('[data-testid="agent-attachments-section"]')
    expect(appConfigTargets).not.toContain('[data-testid="agent-vision-section"]')
    expect(appConfigTargets).not.toContain('[data-testid="agent-file-upload-section"]')
    expect(knowledgeBaseTargets).not.toContain('[data-testid="kb-dialog-rerank-fail-open"]')
  })

  test('looks up known tours and returns undefined for unknown IDs', () => {
    expect(getTourConfigById('kb')).toBe(allTourConfigs[2])
    expect(getTourConfigById('unknown')).toBeUndefined()
  })

  test('selects the configured auto-start tour', () => {
    const expected = allTourConfigs.find(config => config.autoStart)?.id ?? null
    expect(getAutoStartTour()).toBe(expected)
  })
})
