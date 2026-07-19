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
import { OnboardingTour } from './onboarding-tour'

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

function installSpies() {
  const spies = [
    spyOn(navigation, 'useRouter').mockReturnValue({ push } as ReturnType<typeof navigation.useRouter>),
    spyOn(navigation, 'usePathname').mockImplementation(() => pathname),
    spyOn(navigation, 'useSearchParams').mockImplementation(
      () => query as ReturnType<typeof navigation.useSearchParams>,
    ),
    spyOn(intl, 'useTranslations').mockReturnValue(((key: string) => key) as ReturnType<typeof intl.useTranslations>),
    spyOn(teamContext, 'useTeam').mockReturnValue({ currentTeam: { id: 'team-1' }, isLoading: false } as ReturnType<typeof teamContext.useTeam>),
    spyOn(onboardingProvider, 'useOnboarding').mockImplementation(() => ({
      state, startTour, nextStep, goToStep, completeTour,
    }) as ReturnType<typeof onboardingProvider.useOnboarding>),
    spyOn(platformSteps, 'getTourConfigById').mockImplementation(id => id === config.id ? config : undefined),
    spyOn(joyride, 'Joyride').mockImplementation(props => {
      joyrideProps = props
      return null
    }),
  ]
  return () => spies.reverse().forEach(spy => spy.mockRestore())
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
})
