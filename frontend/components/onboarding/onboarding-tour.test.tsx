import { afterAll, afterEach, beforeAll, describe, expect, it, mock, spyOn } from 'bun:test'
import { GlobalRegistrator } from '@happy-dom/global-registrator'
import { act, cleanup, render, waitFor } from '@testing-library/react'
import * as React from 'react'
import * as navigation from 'next/navigation'
import * as intl from 'next-intl'
import * as joyride from 'react-joyride'
import * as teamContext from '@/contexts/team-context'
import * as onboardingProvider from './onboarding-provider'
import * as platformSteps from './steps/platform-steps'
import type { OnboardingTourConfig } from './steps/types'
import { OnboardingTour, allTourIds } from './onboarding-tour'

const push = mock(() => {})
const startTour = mock(() => {})
const nextStep = mock(() => {})
const goToStep = mock(() => {})
const completeTour = mock(() => {})
let pathname = '/app'
let query = new URLSearchParams()
let state = {
  completedTours: [] as onboardingProvider.OnboardingTourId[],
  currentTour: null as onboardingProvider.OnboardingTourId | null,
  currentStep: 0,
  isRunning: false,
}
let joyrideProps: React.ComponentProps<typeof joyride.Joyride> | undefined
let config: OnboardingTourConfig

function installSpies(mockJoyride = true, mockOnboarding = true) {
  const spies = [
    spyOn(navigation, 'useRouter').mockReturnValue({ push } as ReturnType<typeof navigation.useRouter>),
    spyOn(navigation, 'usePathname').mockImplementation(() => pathname),
    spyOn(navigation, 'useSearchParams').mockImplementation(
      () => query as ReturnType<typeof navigation.useSearchParams>,
    ),
    spyOn(intl, 'useTranslations').mockReturnValue(((key: string) => key) as ReturnType<typeof intl.useTranslations>),
    spyOn(teamContext, 'useTeam').mockReturnValue({ currentTeam: { id: 'team-1' }, isLoading: false } as ReturnType<typeof teamContext.useTeam>),
    spyOn(platformSteps, 'getTourConfigById').mockImplementation(id => id === config.id ? config : undefined),
  ]
  const onboardingSpy = mockOnboarding
    ? spyOn(onboardingProvider, 'useOnboarding').mockImplementation(() => ({
        state, startTour, nextStep, goToStep, completeTour,
      }) as ReturnType<typeof onboardingProvider.useOnboarding>)
    : null
  const joyrideSpy = mockJoyride
    ? spyOn(joyride, 'Joyride').mockImplementation(props => {
        joyrideProps = props
        return null
      })
    : null
  return () => {
    joyrideSpy?.mockRestore()
    onboardingSpy?.mockRestore()
    spies.reverse().forEach(spy => spy.mockRestore())
  }
}

beforeAll(() => GlobalRegistrator.register())
afterEach(() => {
  cleanup()
  mock.restore()
  push.mockClear()
  startTour.mockClear()
  nextStep.mockClear()
  goToStep.mockClear()
  completeTour.mockClear()
  pathname = '/app'
  query = new URLSearchParams()
  state = { completedTours: [], currentTour: null, currentStep: 0, isRunning: false }
  joyrideProps = undefined
})
afterAll(() => GlobalRegistrator.unregister())

describe('OnboardingTour', () => {
  it('does not render dashboard-only tour configs in platform layouts', () => {
    expect(allTourIds).toContain('overview')
    expect(allTourIds).not.toContain('adminModelSetup')
  })

  it('auto-starts overview once only when the home/team/completion boundaries allow it', async () => {
    config = {
      id: 'overview', title: 'Overview', description: '', autoStart: true,
      steps: [{ target: 'body', content: 'Welcome' }],
    }
    const restore = installSpies()
    const view = render(<OnboardingTour tourId="overview" />)

    await waitFor(() => expect(startTour).toHaveBeenCalledWith('overview'), { timeout: 800 })
    view.rerender(<OnboardingTour tourId="overview" />)
    await act(() => new Promise(resolve => setTimeout(resolve, 550)))
    expect(startTour).toHaveBeenCalledTimes(1)
    restore()
  })

  it('does not auto-start a completed overview tour', async () => {
    config = {
      id: 'overview', title: 'Overview', description: '', autoStart: true,
      steps: [{ target: 'body', content: 'Welcome' }],
    }
    state.completedTours = ['overview']
    const restore = installSpies()
    render(<OnboardingTour tourId="overview" />)

    await act(() => new Promise(resolve => setTimeout(resolve, 550)))
    expect(startTour).not.toHaveBeenCalled()
    restore()
  })

  it('starts from URL once and clamps steps to valid boundaries', () => {
    config = {
      id: 'models', title: 'Models', description: '',
      steps: [
        { target: 'body', content: 'one' },
        { target: 'body', content: 'two' },
      ],
    }
    query = new URLSearchParams('tour=models&step=99')
    const restore = installSpies()
    const view = render(<OnboardingTour tourId="models" />)

    expect(startTour).toHaveBeenCalledWith('models', 1)
    view.rerender(<OnboardingTour tourId="models" />)
    expect(startTour).toHaveBeenCalledTimes(1)
    restore()
  })

  it('clamps URL step indexes after filtering missing optional targets', () => {
    const available = document.createElement('div')
    available.className = 'available'
    document.body.appendChild(available)
    config = {
      id: 'models', title: 'Models', description: '',
      steps: [
        { target: 'body', content: 'one' },
        { target: '.missing', content: 'two', skipIfMissing: true },
        { target: '.available', content: 'three', skipIfMissing: true },
      ],
    }
    query = new URLSearchParams('tour=models&step=2')
    const restore = installSpies()
    render(<OnboardingTour tourId="models" />)

    expect(startTour).toHaveBeenCalledWith('models', 1)

    available.remove()
    restore()
  })

  it('starts the real Joyride tour through the real onboarding provider', async () => {
    const canvas = document.createElement('div')
    canvas.dataset.testid = 'workflow-canvas'
    canvas.style.width = '800px'
    canvas.style.height = '600px'
    document.body.appendChild(canvas)
    config = platformSteps.getTourConfigById('workflowConfig')!
    const restore = installSpies(false, false)

    function Trigger() {
      const onboarding = onboardingProvider.useOptionalOnboarding()
      return <button onClick={() => setTimeout(() => onboarding?.startTour('workflowConfig'), 300)}>start</button>
    }

    const view = render(
      <onboardingProvider.OnboardingProvider>
        <Trigger />
        <OnboardingTour tourId="workflowConfig" />
      </onboardingProvider.OnboardingProvider>
    )
    view.getByText('start').click()

    await waitFor(() => expect(document.body.textContent).toContain('onboarding.step20a.description'), { timeout: 2000 })
    expect((document.querySelector('.react-joyride__floater') as HTMLElement | null)?.style.position).toBe('fixed')

    canvas.remove()
    restore()
  })

  it('navigates before advancing and treats /app as an exact route boundary', async () => {
    config = {
      id: 'models', title: 'Models', description: '',
      steps: [
        { target: 'body', content: 'one' },
        { target: 'body', content: 'two', route: '/app' },
      ],
    }
    pathname = '/app/models'
    state = { completedTours: [], currentTour: 'models', currentStep: 0, isRunning: true }
    const restore = installSpies()
    render(<OnboardingTour tourId="models" />)

    act(() => joyrideProps?.onEvent?.(
      { action: joyride.ACTIONS.NEXT, type: joyride.EVENTS.STEP_AFTER },
      {} as joyride.Controls,
    ))
    expect(push).toHaveBeenCalledWith('/app')
    expect(nextStep).not.toHaveBeenCalled()
    await waitFor(() => expect(nextStep).toHaveBeenCalled(), { timeout: 800 })
    restore()
  })
  it('keeps KB detail and search descendants on the current route family', () => {
    for (const nestedPath of ['/app/kb/kb-1', '/app/kb/kb-1/search']) {
      config = {
        id: 'kb', title: 'Knowledge Base', description: '',
        steps: [{ target: 'body', content: 'detail', route: '/app/kb' }],
      }
      pathname = nestedPath
      state = { completedTours: [], currentTour: 'kb', currentStep: 0, isRunning: true }
      const restore = installSpies()
      const view = render(<OnboardingTour tourId="kb" />)

      expect(push).not.toHaveBeenCalledWith('/app/kb')
      view.unmount()
      restore()
      push.mockClear()
    }
  })

  it('completes on Joyride close statuses and on the final custom action', () => {
    config = {
      id: 'models', title: 'Models', description: '',
      steps: [{ target: 'body', title: 'Title', content: 'Content' }],
    }
    state = { completedTours: [], currentTour: 'models', currentStep: 0, isRunning: true }
    const restore = installSpies()
    render(<OnboardingTour tourId="models" />)

    act(() => joyrideProps?.onEvent?.(
      { status: joyride.STATUS.SKIPPED },
      {} as joyride.Controls,
    ))
    expect(completeTour).toHaveBeenCalledWith('models')

    const Tooltip = joyrideProps?.tooltipComponent
    expect(Tooltip).toBeDefined()
    const tooltip = render(<Tooltip
      index={0}
      isLastStep
      step={config.steps[0]}
      size={1}
    />)
    tooltip.getByText('onboarding.finish').click()
    expect(completeTour).toHaveBeenCalledTimes(2)
    restore()
  })

  it('skips a missing last target but advances past a missing middle target', async () => {
    config = {
      id: 'models', title: 'Models', description: '',
      steps: [
        { target: 'body', content: 'one' },
        { target: '.missing', content: 'two' },
      ],
    }
    state = { completedTours: [], currentTour: 'models', currentStep: 0, isRunning: true }
    const restore = installSpies()
    render(<OnboardingTour tourId="models" />)

    act(() => joyrideProps?.onEvent?.(
      { action: joyride.ACTIONS.NEXT, type: joyride.EVENTS.TARGET_NOT_FOUND },
      {} as joyride.Controls,
    ))
    await waitFor(() => expect(completeTour).toHaveBeenCalledWith('models'), { timeout: 800 })
    expect(nextStep).not.toHaveBeenCalled()
    restore()
  })

  it('filters optional missing targets before mounting Joyride', () => {
    const available = document.createElement('div')
    available.className = 'available'
    document.body.appendChild(available)
    config = {
      id: 'models', title: 'Models', description: '',
      steps: [
        { target: 'body', content: 'one' },
        { target: '.available', content: 'two', skipIfMissing: true },
        { target: '.optional-missing', content: 'three', skipIfMissing: true },
        { target: '.required-missing', content: 'four' },
      ],
    }
    state = { completedTours: [], currentTour: 'models', currentStep: 0, isRunning: true }
    const restore = installSpies()
    render(<OnboardingTour tourId="models" />)

    expect(joyrideProps?.steps.map(step => step.target)).toEqual([
      'body',
      '.available',
      '.required-missing',
    ])

    available.remove()
    restore()
  })

  it('detects the first available target and cancels lifecycle timers on unmount', async () => {
    const available = document.createElement('div')
    available.className = 'available'
    document.body.appendChild(available)
    config = {
      id: 'overview', title: 'Overview', description: '', autoStart: true,
      steps: [
        { target: '.missing', content: 'one' },
        { target: '.available', content: 'two' },
      ],
    }
    state = { completedTours: [], currentTour: 'overview', currentStep: 0, isRunning: true }
    const restore = installSpies()
    const view = render(<OnboardingTour tourId="overview" />)

    await waitFor(() => expect(goToStep).toHaveBeenCalledWith(1), { timeout: 600 })
    state = { completedTours: [], currentTour: null, currentStep: 0, isRunning: false }
    view.rerender(<OnboardingTour tourId="overview" />)
    view.unmount()
    await act(() => new Promise(resolve => setTimeout(resolve, 550)))
    expect(startTour).not.toHaveBeenCalled()

    available.remove()
    restore()
  })

  it('guards automatic routing for navigation-only steps and matching routes', () => {
    config = {
      id: 'models', title: 'Models', description: '',
      steps: [{
        target: 'body', content: 'one', route: '/app/models',
        advanceOnClick: true, waitForRouteChange: true,
      }],
    }
    pathname = '/app'
    state = { completedTours: [], currentTour: 'models', currentStep: 0, isRunning: true }
    const restore = installSpies()
    const view = render(<OnboardingTour tourId="models" />)
    expect(push).not.toHaveBeenCalled()

    config = {
      ...config,
      steps: [{ target: 'body', content: 'one', route: '/app/models' }],
    }
    pathname = '/app/models'
    view.rerender(<OnboardingTour tourId="models" />)
    expect(push).not.toHaveBeenCalled()

    pathname = '/app'
    view.rerender(<OnboardingTour tourId="models" />)
    expect(push).toHaveBeenCalledWith('/app/models')
    restore()
  })

  it('handles keyboard navigation, focus guards, dismissal, and listener cleanup', () => {
    config = {
      id: 'models', title: 'Models', description: '',
      steps: [
        { target: 'body', content: 'one' },
        { target: 'body', content: 'two' },
      ],
    }
    state = { completedTours: [], currentTour: 'models', currentStep: 0, isRunning: true }
    const restore = installSpies()
    const view = render(<OnboardingTour tourId="models" />)
    const input = document.createElement('input')
    document.body.appendChild(input)
    input.focus()

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', ctrlKey: true, bubbles: true }))
    expect(nextStep).not.toHaveBeenCalled()
    input.blur()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', metaKey: true, bubbles: true }))
    expect(nextStep).toHaveBeenCalledTimes(1)

    const Tooltip = joyrideProps?.tooltipComponent
    expect(Tooltip).toBeDefined()
    render(<Tooltip index={0} isLastStep={false} step={config.steps[0]} size={2} />)
      .getByText('onboarding.skip').click()
    expect(completeTour).toHaveBeenCalledWith('models')

    view.unmount()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', ctrlKey: true, bubbles: true }))
    expect(nextStep).toHaveBeenCalledTimes(1)
    input.remove()
    restore()
  })

  it('advances from target clicks and inputs once, then removes their listeners', async () => {
    const button = document.createElement('button')
    button.className = 'advance-target'
    const input = document.createElement('input')
    input.className = 'advance-input'
    document.body.append(button, input)
    config = {
      id: 'models', title: 'Models', description: '',
      steps: [
        { target: '.advance-target', content: 'click', advanceOnClick: true },
        { target: '.advance-input', content: 'type', advanceOnInput: true },
      ],
    }
    state = { completedTours: [], currentTour: 'models', currentStep: 0, isRunning: true }
    const restore = installSpies()
    const view = render(<OnboardingTour tourId="models" />)

    button.click()
    button.click()
    await waitFor(() => expect(nextStep).toHaveBeenCalledTimes(1), { timeout: 600 })

    state = { ...state, currentStep: 1 }
    view.rerender(<OnboardingTour tourId="models" />)
    input.value = '  '
    input.dispatchEvent(new Event('input', { bubbles: true }))
    expect(nextStep).toHaveBeenCalledTimes(1)
    input.value = 'ready'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    input.dispatchEvent(new Event('input', { bubbles: true }))
    await waitFor(() => expect(completeTour).toHaveBeenCalledWith('models'), { timeout: 600 })

    view.unmount()
    input.value = 'again'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    await act(() => new Promise(resolve => setTimeout(resolve, 350)))
    expect(completeTour).toHaveBeenCalledTimes(1)
    button.remove()
    input.remove()
    restore()
  })

  it('adds the dialog overlay class only while dialog steps are mounted', () => {
    config = {
      id: 'appCreate', title: 'Create app', description: '',
      steps: [{ target: '.app-create-name-input', content: 'name' }],
    }
    state = { completedTours: [], currentTour: 'appCreate', currentStep: 0, isRunning: true }
    const restore = installSpies()
    const appCreateView = render(<OnboardingTour tourId="appCreate" />)

    expect(document.body.classList.contains('joyride-dialog-active')).toBe(true)
    appCreateView.unmount()
    expect(document.body.classList.contains('joyride-dialog-active')).toBe(false)

    config = {
      id: 'adminModelSetup', title: 'Admin model setup', description: '',
      steps: [{ target: '.admin-model-dialog-provider-selection', content: 'provider' }],
    }
    state = { completedTours: [], currentTour: 'adminModelSetup', currentStep: 0, isRunning: true }
    const adminModelSetupView = render(<OnboardingTour tourId="adminModelSetup" />)

    expect(document.body.classList.contains('joyride-dialog-active')).toBe(true)
    adminModelSetupView.unmount()
    expect(document.body.classList.contains('joyride-dialog-active')).toBe(false)
    restore()

    for (const target of [
      '[data-testid="kb-upload-dialog"]',
      '[data-testid="kb-upload-dialog-cancel"]',
      '[data-testid="kb-import-url-dialog"]',
      '[data-testid="kb-import-url-dialog-cancel"]',
    ]) {
      config = { id: 'kb', title: 'Knowledge Base', description: '', steps: [{ target, content: 'dialog' }] }
      state = { completedTours: [], currentTour: 'kb', currentStep: 0, isRunning: true }
      const kbRestore = installSpies()
      const kbView = render(<OnboardingTour tourId="kb" />)

      expect(document.body.classList.contains('joyride-dialog-active')).toBe(true)
      kbView.unmount()
      expect(document.body.classList.contains('joyride-dialog-active')).toBe(false)
      kbRestore()
    }
  })
})
