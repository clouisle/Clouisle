import type { SVGProps } from 'react'

// Vendored from lobehub/lobe-icons v6.9.1 (MIT). See ./LICENSE.
export function BaichuanIcon({ size = 16, ...props }: SVGProps<SVGSVGElement> & { size?: number | string }) {
  return (
    <svg
      aria-hidden="true"
      fill="currentColor" fillRule="evenodd"
      height={size}
      viewBox="0 0 24 24"
      width={size}
      xmlns="http://www.w3.org/2000/svg"
      {...props}
    >
<path d="M7.333 2h-3.2l-2 4.333V17.8L0 22h5.2l2.028-4.2L7.333 2zm7.334 0h-5.2v20h5.2V2zM16.8 7.733H22V22h-5.2V7.733zM22 2h-5.2v4.133H22V2z" />
    </svg>
  )
}
