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
      'adminModelSetup',
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
    const adminModelSetup = getTourConfigById('adminModelSetup')

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
    expect(getTourConfigById('workflowConfig')?.steps[0]?.placement).toBe('center')
    expect(adminModelSetup).toMatchObject({
      id: 'adminModelSetup',
      showInPlatformMenu: false,
      steps: [
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
      ],
    })
    expect(adminModelSetup?.steps).toHaveLength(7)
  })

  test('looks up known tours and returns undefined for unknown IDs', () => {
    expect(getTourConfigById('kb')).toBe(allTourConfigs[2])
    expect(getTourConfigById('adminModelSetup')).toBe(allTourConfigs[7])
    expect(getTourConfigById('unknown')).toBeUndefined()
  })

  test('selects the configured auto-start tour', () => {
    const expected = allTourConfigs.find(config => config.autoStart)?.id ?? null
    expect(getAutoStartTour()).toBe(expected)
  })
})
