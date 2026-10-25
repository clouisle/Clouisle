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
import { integrationsApi, type Integration, type IntegrationCreate, type IntegrationType } from '@/lib/api/admin/integrations'
import type { IntegrationProviderType } from '@/lib/api/integrations'
import { clearValidationError, clearValidationErrorsByPrefix, getValidationSummaryEntries, mapValidationErrors, normalizeValidationErrors,
  formatValidationSummaryMessage
} from '@/lib/validation'
import { useCanPerform } from '@/components/permission-guard'
import { FieldError } from '@/components/ui/field'

interface LoginIntegrationDialogProps {
  open: boolean
  provider: Integration | null
  types: IntegrationType[]
  onClose: (success?: boolean) => void
}

const PROVIDER_NAME_REGEX = /^[a-z][a-z0-9_-]*$/
const PROVIDER_ERROR_PATH_MAP = {
  config: 'config',
  attribute_mapping: 'attribute_mapping',
  display_name: 'display_name',
  icon_url: 'icon_url',
  button_text: 'button_text',
  credentials: 'credentials',
  'login_config.default_role_id': 'default_role_id',
} as const
export function LoginIntegrationDialog({ open, provider, types, onClose }: LoginIntegrationDialogProps) {
  const t = useTranslations('sso')
  const { canPerform } = useCanPerform()
  const canUpdate = canPerform('admin:integrations:login:update')
  const [loading, setLoading] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [formData, setFormData] = useState({
    name: '',
    provider_type: 'oidc' as IntegrationProviderType,
    display_name: '',
    icon_url: '',
    button_text: '',
    is_enabled: true,
    allow_signup: true,
    require_approval: false,
    default_role_id: '',
    credentials: '{}',
    config: '{}',
    attribute_mapping: '{}',
  })

  useEffect(() => {
    setFieldErrors({})
    if (provider) {
      setFormData({
        name: provider.name,
        provider_type: provider.provider_type,
        display_name: provider.display_name,
        icon_url: provider.icon_url || '',
        button_text: provider.button_text || '',
        is_enabled: provider.is_enabled,
        allow_signup: provider.login_config.allow_signup,
        require_approval: provider.login_config.require_approval,
        default_role_id: provider.login_config.default_role_id || '',
        credentials: '{}',
        config: JSON.stringify(provider.config, null, 2),
        attribute_mapping: JSON.stringify(provider.attribute_mapping, null, 2),
      })
    } else {
      const providerType = types.find((type) => type.provider_type === 'oidc')?.provider_type || types[0]?.provider_type || 'oidc'
      setFormData({
        name: '',
        provider_type: providerType,
        display_name: '',
        icon_url: '',
        button_text: '',
        is_enabled: true,
        allow_signup: true,
        require_approval: false,
        default_role_id: '',
        credentials: '{}',
        config: JSON.stringify(getDefaultConfig(providerType), null, 2),
        attribute_mapping: JSON.stringify(getDefaultAttributeMapping(), null, 2),
      })
    }
  }, [provider, open, types])

  const getDefaultConfig = (provider_type: string) => {
    switch (provider_type) {
      case 'oauth2':
      case 'oidc':
        return {
          client_id: '',
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

  const handleProtocolChange = (provider_type: string | null) => {
    if (!provider_type || !types.some((type) => type.provider_type === provider_type)) return
    setFormData({
      ...formData,
      provider_type: provider_type as IntegrationProviderType,
      config: JSON.stringify(getDefaultConfig(provider_type), null, 2),
    })
  }

  const summaryEntries = getValidationSummaryEntries(
    fieldErrors,
    ['name', 'display_name', 'icon_url', 'button_text', 'config', 'credentials', 'attribute_mapping', 'default_role_id']
  )

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!canUpdate) return
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
      let credentials: Record<string, string>
      try {
        credentials = JSON.parse(formData.credentials)
        if (!credentials || Array.isArray(credentials) || typeof credentials !== 'object' || Object.values(credentials).some((value) => typeof value !== 'string')) throw new Error('Invalid credentials')
      } catch {
        setFieldErrors({ credentials: t('invalidCredentialsJson') })
        return
      }

      const data: IntegrationCreate = {
        name: formData.name,
        provider_type: formData.provider_type,
        display_name: formData.display_name,
        icon_url: formData.icon_url || null,
        button_text: formData.button_text || null,
        is_enabled: formData.is_enabled,
        enabled_capabilities: ['user_login'],
        credentials,
        login_config: {
          allow_signup: formData.allow_signup,
          require_approval: formData.require_approval,
          default_role_id: formData.default_role_id || null,
        },
        config,
        attribute_mapping,
      }

      if (provider) {
        await integrationsApi.update(provider.id, data)
        toast.success(t('updateSuccess'))
      } else {
        await integrationsApi.create(data)
        toast.success(t('createSuccess'))
      }

      onClose(true)
    } catch (error: unknown) {
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
                  <Label htmlFor="provider_type">{t('protocol')} *</Label>
                  <Select
                    value={formData.provider_type}
                    onValueChange={handleProtocolChange}
                    disabled={!!provider || !canUpdate}
                  >
                    <SelectTrigger>
                      <SelectValue>{types.find((type) => type.provider_type === formData.provider_type)?.display_name || provider?.provider_type || t('protocol')}</SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      {types.map((type) => <SelectItem key={type.provider_type} value={type.provider_type}>{type.display_name}</SelectItem>)}
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
                <div className="space-y-2">
                  <Label htmlFor="default_role_id">{t('defaultRole')}</Label>
                  <Input id="default_role_id" value={formData.default_role_id} disabled={!canUpdate} onChange={(event) => setFormData({ ...formData, default_role_id: event.target.value })} aria-invalid={!!fieldErrors.default_role_id} />
                  <FieldError>{fieldErrors.default_role_id}</FieldError>
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
              <div className="space-y-2">
                <Label htmlFor="credentials">{t('credentialsJson')}</Label>
                <Textarea id="credentials" value={formData.credentials} rows={5} className="font-mono text-sm" disabled={!canUpdate} aria-invalid={!!fieldErrors.credentials} onChange={(event) => { setFormData({ ...formData, credentials: event.target.value }); setFieldErrors((current) => clearValidationErrorsByPrefix(current, 'credentials')) }} />
                <FieldError>{fieldErrors.credentials}</FieldError>
                <p className="text-xs text-muted-foreground">{t('credentialsHint')}{provider?.credentials_configured.length ? ` (${provider.credentials_configured.join(', ')})` : ''}</p>
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
