'use client'

import { useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ssoApi, type SSOProviderAdmin, type SSOProviderCreate } from '@/lib/api/admin/sso'
import { clearValidationError, clearValidationErrorsByPrefix, getValidationSummaryEntries, mapValidationErrors, normalizeValidationErrors,
  formatValidationSummaryMessage
} from '@/lib/validation'
import { useCanPerform } from '@/components/permission-guard'
import { FieldError } from '@/components/ui/field'

interface ProviderDialogProps {
  open: boolean
  provider: SSOProviderAdmin | null
  onClose: (success?: boolean) => void
}

const PROVIDER_NAME_REGEX = /^[a-z][a-z0-9_-]*$/
const PROVIDER_ERROR_PATH_MAP = {
  config: 'config',
  attribute_mapping: 'attribute_mapping',
  display_name: 'display_name',
  icon_url: 'icon_url',
  button_text: 'button_text',
} as const

export function ProviderDialog({ open, provider, onClose }: ProviderDialogProps) {
  const t = useTranslations('sso')
  const { canPerform } = useCanPerform()
  const canUpdate = canPerform('admin:sso:update')
  const [loading, setLoading] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [formData, setFormData] = useState({
    name: '',
    protocol: 'oidc',
    display_name: '',
    icon_url: '',
    button_text: '',
    is_enabled: true,
    allow_signup: true,
    require_approval: false,
    config: '{}',
    attribute_mapping: '{}',
  })

  useEffect(() => {
    setFieldErrors({})
    if (provider) {
      setFormData({
        name: provider.name,
        protocol: provider.protocol,
        display_name: provider.display_name,
        icon_url: provider.icon_url || '',
        button_text: provider.button_text || '',
        is_enabled: provider.is_enabled,
        allow_signup: provider.allow_signup,
        require_approval: provider.require_approval,
        config: JSON.stringify(provider.config, null, 2),
        attribute_mapping: JSON.stringify(provider.attribute_mapping, null, 2),
      })
    } else {
      setFormData({
        name: '',
        protocol: 'oidc',
        display_name: '',
        icon_url: '',
        button_text: '',
        is_enabled: true,
        allow_signup: true,
        require_approval: false,
        config: JSON.stringify(getDefaultConfig('oidc'), null, 2),
        attribute_mapping: JSON.stringify(getDefaultAttributeMapping(), null, 2),
      })
    }
  }, [provider, open])

  const getDefaultConfig = (protocol: string) => {
    switch (protocol) {
      case 'oidc':
        return {
          client_id: '',
          client_secret: '',
          authorization_url: '',
          token_url: '',
          userinfo_url: '',
          scopes: 'openid email profile',
        }
      case 'saml2':
        return {
          sp_entity_id: '',
          idp_entity_id: '',
          sso_url: '',
          slo_url: '',
          x509_cert: '',
          acs_url: '',
        }
      case 'cas':
        return {
          server_url: '',
          service_url: '',
          version: '3',
        }
      default:
        return {}
    }
  }

  const getDefaultAttributeMapping = () => {
    return {
      email: 'email',
      username: 'name',
      avatar_url: 'picture',
    }
  }

  const handleProtocolChange = (protocol: string | null) => {
    if (!protocol) return
    setFormData({
      ...formData,
      protocol,
      config: JSON.stringify(getDefaultConfig(protocol), null, 2),
    })
  }

  const summaryEntries = getValidationSummaryEntries(
    fieldErrors,
    ['name', 'display_name', 'icon_url', 'button_text', 'config', 'attribute_mapping']
  )

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setFieldErrors({})

    // Validate provider name format
    const errors: Record<string, string> = {}
    if (!provider && !PROVIDER_NAME_REGEX.test(formData.name)) {
      errors.name = t('invalidProviderName')
    }

    // Validate icon URL format
    if (formData.icon_url && !/^https?:\/\//.test(formData.icon_url)) {
      errors.icon_url = t('invalidIconUrl')
    }

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors)
      return
    }

    setLoading(true)

    try {
      // Validate JSON
      let config: Record<string, unknown>
      let attribute_mapping: Record<string, string>

      try {
        config = JSON.parse(formData.config)
      } catch {
        setFieldErrors({ config: t('invalidConfigJson') || 'Invalid configuration JSON' })
        setLoading(false)
        return
      }

      try {
        attribute_mapping = JSON.parse(formData.attribute_mapping) as Record<string, string>
      } catch {
        setFieldErrors({ attribute_mapping: t('invalidMappingJson') || 'Invalid attribute mapping JSON' })
        setLoading(false)
        return
      }

      const data: SSOProviderCreate = {
        name: formData.name,
        protocol: formData.protocol,
        display_name: formData.display_name,
        icon_url: formData.icon_url || null,
        button_text: formData.button_text || null,
        is_enabled: formData.is_enabled,
        allow_signup: formData.allow_signup,
        require_approval: formData.require_approval,
        config,
        attribute_mapping,
      }

      if (provider) {
        await ssoApi.updateProvider(provider.id, data)
        toast.success(t('updateSuccess'))
      } else {
        await ssoApi.createProvider(data)
        toast.success(t('createSuccess'))
      }

      onClose(true)
    } catch (error) {
      const errors = mapValidationErrors(normalizeValidationErrors(error), PROVIDER_ERROR_PATH_MAP)
      if (Object.keys(errors).length > 0) {
        setFieldErrors(errors)
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={() => onClose()}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {provider ? t('editProvider') : t('addProvider')}
          </DialogTitle>
          <DialogDescription>
            {provider
              ? t('editProviderDescription')
              : t('addProviderDescription')}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {summaryEntries.length > 0 && (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 space-y-1">
              {summaryEntries.map(([field, message]) => (
                <FieldError key={field}>
                  {formatValidationSummaryMessage(field, message)}
                </FieldError>
              ))}
            </div>
          )}
          <Tabs defaultValue="basic" className="w-full">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="basic">{t('basicInfo')}</TabsTrigger>
              <TabsTrigger value="config">{t('configuration')}</TabsTrigger>
              <TabsTrigger value="mapping">{t('attributeMapping')}</TabsTrigger>
            </TabsList>

            <TabsContent value="basic" className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="name">{t('providerName')} *</Label>
                  <Input
                    id="name"
                    value={formData.name}
                    onChange={(e) => {
                      setFormData({ ...formData, name: e.target.value })
                      setFieldErrors((prev) => clearValidationError(prev, 'name'))
                    }}
                    placeholder="google"
                    required
                    disabled={!!provider || !canUpdate}
                    aria-invalid={!!fieldErrors.name}
                  />
                  {fieldErrors.name ? (
                    <FieldError>{fieldErrors.name}</FieldError>
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      {t('providerNameHint')}
                    </p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="protocol">{t('protocol')} *</Label>
                  <Select
                    value={formData.protocol}
                    onValueChange={handleProtocolChange}
                    disabled={!!provider || !canUpdate}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="oidc">OAuth2/OIDC</SelectItem>
                      <SelectItem value="saml2">SAML 2.0</SelectItem>
                      <SelectItem value="cas">CAS</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="display_name">{t('displayName')} *</Label>
                <Input
                  id="display_name"
                  value={formData.display_name}
                  onChange={(e) => {
                    setFormData({ ...formData, display_name: e.target.value })
                    setFieldErrors((prev) => clearValidationError(prev, 'display_name'))
                  }}
                  placeholder="Google"
                  required
                  disabled={!canUpdate}
                  aria-invalid={!!fieldErrors.display_name}
                />
                <FieldError>{fieldErrors.display_name}</FieldError>
              </div>

              <div className="space-y-2">
                <Label htmlFor="button_text">{t('buttonText')}</Label>
                <Input
                  id="button_text"
                  value={formData.button_text}
                  onChange={(e) => {
                    setFormData({ ...formData, button_text: e.target.value })
                    setFieldErrors((prev) => clearValidationError(prev, 'button_text'))
                  }}
                  placeholder="Sign in with Google"
                  disabled={!canUpdate}
                  aria-invalid={!!fieldErrors.button_text}
                />
                <FieldError>{fieldErrors.button_text}</FieldError>
              </div>

              <div className="space-y-2">
                <Label htmlFor="icon_url">{t('iconUrl')}</Label>
                <Input
                  id="icon_url"
                  value={formData.icon_url}
                  onChange={(e) => {
                    setFormData({ ...formData, icon_url: e.target.value })
                    setFieldErrors((prev) => clearValidationError(prev, 'icon_url'))
                  }}
                  placeholder="https://example.com/icon.png"
                  aria-invalid={!!fieldErrors.icon_url}
                  disabled={!canUpdate}
                />
                <FieldError>{fieldErrors.icon_url}</FieldError>
              </div>

              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label>{t('enabled')}</Label>
                    <p className="text-xs text-muted-foreground">
                      {t('enabledHint')}
                    </p>
                  </div>
                  <Switch
                    checked={formData.is_enabled}
                    onCheckedChange={(checked) =>
                      setFormData({ ...formData, is_enabled: checked })
                    }
                    disabled={!canUpdate}
                  />
                </div>

                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label>{t('allowSignup')}</Label>
                    <p className="text-xs text-muted-foreground">
                      {t('allowSignupHint')}
                    </p>
                  </div>
                  <Switch
                    checked={formData.allow_signup}
                    onCheckedChange={(checked) =>
                      setFormData({ ...formData, allow_signup: checked })
                    }
                    disabled={!canUpdate}
                  />
                </div>

                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label>{t('requireApproval')}</Label>
                    <p className="text-xs text-muted-foreground">
                      {t('requireApprovalHint')}
                    </p>
                  </div>
                  <Switch
                    checked={formData.require_approval}
                    onCheckedChange={(checked) =>
                      setFormData({ ...formData, require_approval: checked })
                    }
                    disabled={!canUpdate}
                  />
                </div>
              </div>
            </TabsContent>

            <TabsContent value="config" className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="config">{t('configurationJson')} *</Label>
                <Textarea
                  id="config"
                  value={formData.config}
                  onChange={(e) => {
                    setFormData({ ...formData, config: e.target.value })
                    setFieldErrors((prev) => clearValidationErrorsByPrefix(prev, 'config'))
                  }}
                  placeholder="{}"
                  rows={15}
                  className="font-mono text-sm"
                  required
                  disabled={!canUpdate}
                  aria-invalid={!!fieldErrors.config}
                />
                <FieldError>{fieldErrors.config}</FieldError>
                <p className="text-xs text-muted-foreground">
                  {t('configurationHint')}
                </p>
              </div>
            </TabsContent>

            <TabsContent value="mapping" className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="attribute_mapping">
                  {t('attributeMappingJson')}
                </Label>
                <Textarea
                  id="attribute_mapping"
                  value={formData.attribute_mapping}
                  onChange={(e) => {
                    setFormData({
                      ...formData,
                      attribute_mapping: e.target.value,
                    })
                    setFieldErrors((prev) => clearValidationErrorsByPrefix(prev, 'attribute_mapping'))
                  }}
                  placeholder="{}"
                  rows={10}
                  className="font-mono text-sm"
                  disabled={!canUpdate}
                  aria-invalid={!!fieldErrors.attribute_mapping}
                />
                <FieldError>{fieldErrors.attribute_mapping}</FieldError>
                <p className="text-xs text-muted-foreground">
                  {t('attributeMappingHint')}
                </p>
              </div>
            </TabsContent>
          </Tabs>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onClose()}
              disabled={loading}
            >
              {t('cancel')}
            </Button>
            <Button type="submit" disabled={loading || !canUpdate}>
              {loading ? t('saving') : t('save')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
