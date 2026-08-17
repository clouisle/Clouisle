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
      'workflowConfig',
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
    const workflowTargets = getTourConfigById('workflowConfig')?.steps.map(step => step.target) ?? []

    expect(appConfigTargets).toContain('[data-testid="agent-attachments-section"]')
    expect(appConfigTargets).not.toContain('[data-testid="agent-vision-section"]')
    expect(appConfigTargets).not.toContain('[data-testid="agent-file-upload-section"]')
    expect(knowledgeBaseTargets).not.toContain('[data-testid="kb-dialog-rerank-fail-open"]')
    expect(workflowTargets).toEqual([
      '[data-testid="workflow-canvas"]',
      '[data-testid="workflow-edit-mode-controls"]',
      '[data-testid="workflow-add-node-button"]',
      '[data-testid^="workflow-node-"] .react-flow__handle',
      '[data-testid^="workflow-node-"]',
      '[data-testid="workflow-validation-checklist"]',
      '[data-testid="workflow-run-button"]',
      '[data-testid="workflow-save-button"]',
      '[data-testid="workflow-settings-button"]',
      '[data-testid="workflow-embed-button"]',
      '[data-testid="workflow-publish-button"]',
    ])
    expect(getTourConfigById('workflowConfig')?.steps.every(step => step.skipIfMissing)).toBe(true)
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
