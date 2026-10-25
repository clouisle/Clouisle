import type { SVGProps } from 'react'

// Vendored from lobehub/lobe-icons v6.9.1 (MIT). See ./LICENSE.
export function LumaIcon({ size = 16, ...props }: SVGProps<SVGSVGElement> & { size?: number | string }) {
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
<path d="M12.393 24L2 17.998l10.393-6 10.392 6-10.393 6z" fillOpacity=".66" />
      <path d="M2 5.999L12.393 0v24L2 18V5.999z" fillOpacity=".66" />
    </svg>
  )
}
