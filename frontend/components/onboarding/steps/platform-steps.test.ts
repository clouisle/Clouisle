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
    const kbConfig = getTourConfigById('kb')
    const knowledgeBaseSubmit = kbConfig?.steps[12]
    expect(knowledgeBaseSubmit).toMatchObject({
      target: '[data-testid="kb-dialog-submit"]',
      route: '/app/kb',
      advanceOnClick: true,
      waitForRouteChange: true,
    })
    const adminModelSetup = getTourConfigById('adminModelSetup')

    expect(appConfigTargets).toContain('[data-testid="agent-attachments-section"]')
    expect(appConfigTargets).not.toContain('[data-testid="agent-vision-section"]')
    expect(appConfigTargets).not.toContain('[data-testid="agent-file-upload-section"]')
    expect(knowledgeBaseTargets).not.toContain('[data-testid="kb-dialog-rerank-fail-open"]')
    expect(knowledgeBaseTargets).toEqual([
      '[data-testid="nav-kb"]',
      '[data-testid="kb-import-button"]',
      '[data-testid="kb-create-card"]',
      '[data-testid="kb-dialog-name"]',
      '[data-testid="kb-dialog-description"]',
      '[data-testid="kb-dialog-embedding"]',
      '[data-testid="kb-dialog-rerank-model"]',
      '[data-testid="kb-dialog-chunk-settings"]',
      '[data-testid="kb-dialog-separator"]',
      '[data-testid="kb-dialog-rerank-section"]',
      '[data-testid="kb-dialog-rerank-enabled"]',
      '[data-testid="kb-dialog-rerank-params"]',
      '[data-testid="kb-dialog-submit"]',
      '[data-testid="kb-detail-page"]',
      '[data-testid="kb-upload-button"]',
      '[data-testid="kb-upload-dialog"]',
      '[data-testid="kb-upload-dialog-cancel"]',
      '[data-testid="kb-import-url-button"]',
      '[data-testid="kb-import-url-dialog"]',
      '[data-testid="kb-import-url-dialog-cancel"]',
      '[data-testid^="kb-document-status-pending-"]',
      '[data-testid^="kb-document-status-processing-"]',
      '[data-testid^="kb-document-status-completed-"]',
      '[data-testid^="kb-document-status-error-"]',
      '[data-testid="kb-search-test-button"]',
      '[data-testid="kb-search-lab"]',
      '[data-testid="kb-search-query"]',
      '[data-testid="kb-search-submit"]',
      '[data-testid="kb-search-results"]',
    ])
    expect(kbConfig?.steps).toHaveLength(29)
    const appendedKbSteps = kbConfig?.steps.slice(13) ?? []
    expect(appendedKbSteps.every(step => step.route === '/app/kb')).toBe(true)
    expect(appendedKbSteps.some(step => step.skipIfMissing)).toBe(false)
    expect(appendedKbSteps.map(step => [step.title, step.content])).toEqual(
      Array.from({ length: 16 }, (_, index) => [`onboarding.step31${String.fromCharCode(97 + index)}.title`, `onboarding.step31${String.fromCharCode(97 + index)}.description`])
    )
    expect(appendedKbSteps[1]).toMatchObject({ advanceOnClick: true, overlayClickAction: false })
    expect(appendedKbSteps[3]).toMatchObject({ advanceOnClick: true, overlayClickAction: false })
    expect(appendedKbSteps[4]).toMatchObject({ advanceOnClick: true, overlayClickAction: false })
    expect(appendedKbSteps[6]).toMatchObject({ advanceOnClick: true, overlayClickAction: false })
    expect(appendedKbSteps[11]).toMatchObject({ advanceOnClick: true, waitForRouteChange: true, overlayClickAction: false })
    expect(kbConfig?.steps[10]?.skipScroll).toBe(true)
    expect(kbConfig?.steps[11]?.skipScroll).toBe(true)
    expect(appendedKbSteps[0]?.placement).toBe('center')
    expect(appendedKbSteps[12]?.placement).toBe('center')
    expect(appendedKbSteps.slice(7, 11).every(step => step.targetWaitTimeout === 0)).toBe(true)
    expect(appendedKbSteps[13]).toMatchObject({ advanceOnInput: true })
    expect(appendedKbSteps[14]).toMatchObject({ advanceOnClick: true })
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
