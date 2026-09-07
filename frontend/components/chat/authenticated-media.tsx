'use client'

import * as React from 'react'
import { useAuthenticatedAssetUrl } from './authenticated-asset'

type AuthenticatedImageProps = Omit<React.ComponentProps<'img'>, 'src'> & {
  src: string
}

type AuthenticatedVideoProps = Omit<React.ComponentProps<'video'>, 'src'> & {
  src: string
}

export function AuthenticatedImage({ src, alt = '', ...props }: AuthenticatedImageProps) {
  const asset = useAuthenticatedAssetUrl(src)
  if (!asset.src) {
    return (
      <span
        role={asset.error ? 'alert' : 'status'}
        aria-label={alt}
        className={props.className}
      />
    )
  }
  return <img {...props} src={asset.src} alt={alt} />
}

export function AuthenticatedVideo({ src, ...props }: AuthenticatedVideoProps) {
  const asset = useAuthenticatedAssetUrl(src)
  if (!asset.src) {
    return <span role={asset.error ? 'alert' : 'status'} className={props.className} />
  }
  return <video {...props} src={asset.src} />
}
