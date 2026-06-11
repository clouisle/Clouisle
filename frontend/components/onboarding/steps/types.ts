import type { Step, Placement } from 'react-joyride'

export interface OnboardingStep extends Step {
  /** Route path for cross-page navigation */
  route?: string
  /** Whether this step requires a specific element to be present */
  waitForElement?: boolean
  /** Delay in ms before showing this step (useful for animations) */
  delay?: number
}

export interface OnboardingTourConfig {
  /** Unique tour identifier */
  id: string
  /** Tour display name */
  title: string
  /** Tour description */
  description: string
  /** Ordered list of steps */
  steps: OnboardingStep[]
  /** Whether this tour should auto-start for new users */
  autoStart?: boolean
  /** Prerequisite tour IDs that must be completed first */
  prerequisites?: string[]
}

export interface OnboardingStepContent {
  title: string
  description: string
  placement?: Placement
}
