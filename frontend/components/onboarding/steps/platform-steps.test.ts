import { describe, expect, test } from 'bun:test'

import {
  allTourConfigs,
  getAutoStartTour,
  getNextTourInChain,
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
      'apiKeys',
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
    expect(appConfigTargets).toContain('[data-testid="embed-config-dialog"]')
    expect(appConfigTargets).toContain('[data-slot="dialog-close"]')
    const embedDialogStep = getTourConfigById('appConfig')?.steps.find(
      step => step.target === '[data-testid="embed-config-dialog"]'
    )
    expect(embedDialogStep?.placement).toBe('bottom')
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
      '[data-testid="kb-documents-table"]',
      '[data-testid="kb-search-test-button"]',
      '[data-testid="kb-search-lab"]',
      '[data-testid="kb-search-query"]',
      '[data-testid="kb-search-submit"]',
      '[data-testid="kb-search-results"]',
    ])
    expect(kbConfig?.steps).toHaveLength(26)
    const appendedKbSteps = kbConfig?.steps.slice(13) ?? []
    expect(appendedKbSteps.every(step => step.route === '/app/kb')).toBe(true)
    expect(appendedKbSteps.some(step => step.skipIfMissing)).toBe(false)
    expect(appendedKbSteps.map(step => [step.title, step.content])).toEqual([
      ['onboarding.step31a.title', 'onboarding.step31a.description'],
      ['onboarding.step31b.title', 'onboarding.step31b.description'],
      ['onboarding.step31c.title', 'onboarding.step31c.description'],
      ['onboarding.step31d.title', 'onboarding.step31d.description'],
      ['onboarding.step31e.title', 'onboarding.step31e.description'],
      ['onboarding.step31f.title', 'onboarding.step31f.description'],
      ['onboarding.step31g.title', 'onboarding.step31g.description'],
      ['onboarding.step31h.title', 'onboarding.step31h.description'],
      ['onboarding.step31l.title', 'onboarding.step31l.description'],
      ['onboarding.step31m.title', 'onboarding.step31m.description'],
      ['onboarding.step31n.title', 'onboarding.step31n.description'],
      ['onboarding.step31o.title', 'onboarding.step31o.description'],
      ['onboarding.step31p.title', 'onboarding.step31p.description'],
    ])
    expect(appendedKbSteps[1]).toMatchObject({ advanceOnClick: true, overlayClickAction: false })
    expect(appendedKbSteps[3]).toMatchObject({ advanceOnClick: true, overlayClickAction: false })
    expect(appendedKbSteps[4]).toMatchObject({ advanceOnClick: true, overlayClickAction: false })
    expect(appendedKbSteps[6]).toMatchObject({ advanceOnClick: true, overlayClickAction: false })
    expect(appendedKbSteps[8]).toMatchObject({ advanceOnClick: true, waitForRouteChange: true, overlayClickAction: false })
    expect(kbConfig?.steps[10]?.skipScroll).toBe(true)
    expect(kbConfig?.steps[11]?.skipScroll).toBe(true)
    expect(appendedKbSteps[0]?.placement).toBe('center')
    expect(appendedKbSteps[9]?.placement).toBe('center')
    expect(appendedKbSteps[10]?.advanceOnInput).toBeUndefined()
    expect(appendedKbSteps[11]).toMatchObject({ advanceOnClick: true })
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
    expect(getTourConfigById('adminModelSetup')).toBe(allTourConfigs[8])
    expect(getTourConfigById('unknown')).toBeUndefined()
  })

  test('wires the prerequisite chain and resolves the next tour in it', () => {
    expect(getTourConfigById('overview')?.prerequisites).toBeUndefined()
    expect(getTourConfigById('models')?.prerequisites).toEqual(['overview'])
    expect(getTourConfigById('kb')?.prerequisites).toEqual(['models'])
    expect(getTourConfigById('appCreate')?.prerequisites).toEqual(['kb'])
    expect(getTourConfigById('appConfig')?.prerequisites).toEqual(['appCreate'])
    expect(getTourConfigById('capabilities')?.prerequisites).toEqual(['appConfig'])
    expect(getTourConfigById('apiKeys')?.prerequisites).toBeUndefined()

    expect(getNextTourInChain('overview')).toBe('models')
    expect(getNextTourInChain('models')).toBe('kb')
    expect(getNextTourInChain('kb')).toBe('appCreate')
    expect(getNextTourInChain('appCreate')).toBe('appConfig')
    expect(getNextTourInChain('appConfig')).toBe('capabilities')
    expect(getNextTourInChain('capabilities')).toBeNull()
  })

  test('registers the apiKeys tour against the page, scope, and dialog surfaces', () => {
    const apiKeys = getTourConfigById('apiKeys')
    expect(apiKeys?.steps.map(step => step.target)).toEqual([
      '[data-testid="api-keys-page"]',
      '[data-testid="api-keys-create-button"]',
      '[data-testid="api-key-name-input"]',
      '[data-testid="api-key-allowed-agents"]',
      '[data-testid="api-key-allowed-workflows"]',
      '[data-testid="api-key-submit"]',
    ])
    expect(apiKeys?.steps.every(step => step.route === '/app/api-keys')).toBe(true)
    expect(apiKeys?.steps.map(step => step.targetWaitTimeout)).toEqual([5000, 5000, 5000, 5000, 5000, 5000])
    expect(apiKeys?.steps[0]?.placement).toBe('center')
    expect(apiKeys?.steps[1]).toMatchObject({ advanceOnClick: true, overlayClickAction: false })
    expect(apiKeys?.steps[3]).toMatchObject({ placement: 'left', overlayClickAction: false })
    expect(apiKeys?.steps[4]).toMatchObject({ placement: 'right', overlayClickAction: false })
    expect(apiKeys?.steps[5]).toMatchObject({
      advanceOnClick: true,
      overlayClickAction: false,
      placement: 'top',
    })
  })

  test('selects the configured auto-start tour', () => {
    const expected = allTourConfigs.find(config => config.autoStart)?.id ?? null
    expect(getAutoStartTour()).toBe(expected)
  })
})
