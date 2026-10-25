import type { SVGProps } from 'react'

/**
 * Neutral gateway mark for custom / OpenAI-compatible endpoints. Locally
 * authored (not a brand mark) so custom gateways never borrow a vendor logo.
 */
export function GatewayIcon({ size = 16, ...props }: SVGProps<SVGSVGElement> & { size?: number | string }) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      height={size}
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={1.8}
      viewBox="0 0 24 24"
      width={size}
      xmlns="http://www.w3.org/2000/svg"
      {...props}
    >
      <circle cx="12" cy="5" r="2.5" />
      <circle cx="5" cy="18" r="2.5" />
      <circle cx="19" cy="18" r="2.5" />
      <path d="M12 7.5v4.5M12 12l-5.2 3.8M12 12l5.2 3.8" />
    </svg>
  )
}
