import type { Step, Placement } from 'react-joyride'

export type OnboardingTourId = 'overview' | 'models' | 'kb' | 'appCreate' | 'appConfig' | 'capabilities'

export interface OnboardingStep extends Step {
  /** Route path for cross-page navigation */
  route?: string
  /** Whether this step requires a specific element to be present */
  waitForElement?: boolean
  /** Delay in ms before showing this step (useful for animations) */
  delay?: number
  /** When true, clicking the spotlight target element advances to the next step */
  advanceOnClick?: boolean
  /** When true, typing in the input field advances to the next step */
  advanceOnInput?: boolean
  /** When true with advanceOnClick, waits for route change before advancing */
  waitForRouteChange?: boolean
}

export interface OnboardingTourConfig {
  /** Unique tour identifier */
  id: OnboardingTourId
  /** Tour display name */
  title: string
  /** Tour description */
  description: string
  /** Ordered list of steps */
  steps: OnboardingStep[]
  /** Whether this tour should auto-start for new users */
  autoStart?: boolean
  /** Prerequisite tour IDs that must be completed first */
  prerequisites?: OnboardingTourId[]
}

export interface OnboardingStepContent {
  title: string
  description: string
  placement?: Placement
}
