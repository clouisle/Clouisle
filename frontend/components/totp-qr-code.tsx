'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Copy, Check, ChevronDown, ChevronUp } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

interface TOTPQRCodeProps {
  secret: string
  qrCode: string
}

export function TOTPQRCode({ secret, qrCode }: TOTPQRCodeProps) {
  const t = useTranslations('auth')
  const [showManual, setShowManual] = React.useState(false)
  const [copied, setCopied] = React.useState(false)

  const handleCopy = async () => {
    await navigator.clipboard.writeText(secret)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="space-y-4">
      {/* QR Code */}
      <div className="flex justify-center">
        <div className="rounded-lg border bg-white p-4">
          <img src={qrCode} alt="TOTP QR Code" className="h-48 w-48" />
        </div>
      </div>

      {/* Manual Entry Toggle */}
      <div className="text-center">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setShowManual(!showManual)}
          className="text-muted-foreground"
        >
          {showManual ? (
            <>
              <ChevronUp className="mr-1 h-4 w-4" />
              {t('setupStep2ManualEntry')}
            </>
          ) : (
            <>
              <ChevronDown className="mr-1 h-4 w-4" />
              {t('setupStep2ManualEntry')}
            </>
          )}
        </Button>
      </div>

      {/* Manual Entry */}
      {showManual && (
        <div className="space-y-2">
          <Label htmlFor="secret">{t('setupStep2ManualEntry')}</Label>
          <div className="flex gap-2">
            <Input
              id="secret"
              value={secret}
              readOnly
              className="font-mono text-sm"
            />
            <Button
              type="button"
              variant="outline"
              size="icon"
              onClick={handleCopy}
            >
              {copied ? (
                <Check className="h-4 w-4 text-green-600" />
              ) : (
                <Copy className="h-4 w-4" />
              )}
            </Button>
          </div>
          {copied && (
            <p className="text-sm text-green-600">{t('setupStep2CodeCopied')}</p>
          )}
        </div>
      )}
    </div>
  )
}
