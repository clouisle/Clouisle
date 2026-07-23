import { afterAll, afterEach, beforeAll, describe, expect, it, spyOn } from 'bun:test'
import { GlobalRegistrator } from '@happy-dom/global-registrator'
import { act, cleanup, fireEvent, render, waitFor, within } from '@testing-library/react'
import * as React from 'react'
import {
  OnboardingProvider,
  useOnboarding,
  useOptionalOnboarding,
} from './onboarding-provider'

const STORAGE_KEY = 'clouisle-onboarding-state'

function StateProbe() {
  const onboarding = useOnboarding()
  return (
    <>
      <output data-testid="state">{JSON.stringify(onboarding.state)}</output>
      <output data-testid="completed">{String(onboarding.isTourCompleted('overview'))}</output>
      <button onClick={() => onboarding.startTour('overview', 2)}>start</button>
      <button onClick={onboarding.prevStep}>previous</button>
      <button onClick={onboarding.nextStep}>next</button>
      <button onClick={() => onboarding.goToStep(4)}>go</button>
      <button onClick={() => onboarding.completeTour('overview')}>complete</button>
      <button onClick={() => onboarding.resetTour('overview')}>reset</button>
      <button onClick={onboarding.resetAllTours}>reset all</button>
      <button onClick={onboarding.stopTour}>stop</button>
    </>
  )
}

function state() {
  return JSON.parse(within(document.body).getByTestId('state').textContent || '{}')
}

beforeAll(() => GlobalRegistrator.register())
afterEach(() => {
  cleanup()
  localStorage.clear()
})
afterAll(() => GlobalRegistrator.unregister())

describe('OnboardingProvider', () => {
  it('loads completed tours and persists only completion state', async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ completedTours: ['overview'] }))
    render(<OnboardingProvider><StateProbe /></OnboardingProvider>)

    await waitFor(() => expect(within(document.body).getByTestId('completed').textContent).toBe('true'))
    expect(state()).toEqual({
      completedTours: ['overview'], currentTour: null, currentStep: 0, isRunning: false,
    })
    expect(localStorage.getItem(STORAGE_KEY)).toBe(
      JSON.stringify({ completedTours: ['overview'] }),
    )
  })

  it('falls back safely for malformed or invalid stored completion data', async () => {
    localStorage.setItem(STORAGE_KEY, '{')
    const { unmount } = render(<OnboardingProvider><StateProbe /></OnboardingProvider>)
    await waitFor(() => expect(localStorage.getItem(STORAGE_KEY)).toBe('{"completedTours":[]}'))
    expect(state().completedTours).toEqual([])

    unmount()
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ completedTours: 'overview' }))
    render(<OnboardingProvider><StateProbe /></OnboardingProvider>)
    await waitFor(() => expect(localStorage.getItem(STORAGE_KEY)).toBe('{"completedTours":[]}'))
    expect(state().completedTours).toEqual([])
  })

  it('starts, bounds previous at zero, navigates steps, and stops', () => {
    render(<OnboardingProvider><StateProbe /></OnboardingProvider>)

    fireEvent.click(within(document.body).getByText('start'))
    expect(state()).toMatchObject({ currentTour: 'overview', currentStep: 2, isRunning: true })
    fireEvent.click(within(document.body).getByText('previous'))
    fireEvent.click(within(document.body).getByText('previous'))
    fireEvent.click(within(document.body).getByText('previous'))
    expect(state().currentStep).toBe(0)
    fireEvent.click(within(document.body).getByText('next'))
    fireEvent.click(within(document.body).getByText('go'))
    expect(state().currentStep).toBe(4)
    fireEvent.click(within(document.body).getByText('stop'))
    expect(state()).toMatchObject({ currentTour: null, currentStep: 0, isRunning: false })
  })

  it('completes idempotently and supports one/all tour resets', () => {
    render(<OnboardingProvider><StateProbe /></OnboardingProvider>)

    fireEvent.click(within(document.body).getByText('complete'))
    fireEvent.click(within(document.body).getByText('complete'))
    expect(state().completedTours).toEqual(['overview'])
    expect(within(document.body).getByTestId('completed').textContent).toBe('true')
    fireEvent.click(within(document.body).getByText('reset'))
    expect(state().completedTours).toEqual([])
    fireEvent.click(within(document.body).getByText('complete'))
    fireEvent.click(within(document.body).getByText('reset all'))
    expect(state()).toEqual({
      completedTours: [], currentTour: null, currentStep: 0, isRunning: false,
    })
  })

  it('exposes an optional empty context and rejects the required hook outside its provider', () => {
    function OptionalProbe() {
      return <output>{String(useOptionalOnboarding())}</output>
    }
    render(<OptionalProbe />)
    expect(within(document.body).getByText('undefined')).toBeTruthy()
    cleanup()

    const consoleError = spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<StateProbe />)).toThrow(
      'useOnboarding must be used within an OnboardingProvider',
    )
    consoleError.mockRestore()
  })

  it('ignores storage write failures', async () => {
    const setItem = spyOn(localStorage, 'setItem').mockImplementation(() => {
      throw new Error('quota')
    })
    render(<OnboardingProvider><StateProbe /></OnboardingProvider>)
    await act(async () => {})
    fireEvent.click(within(document.body).getByText('complete'))
    expect(state().completedTours).toEqual(['overview'])
    setItem.mockRestore()
  })
})
