'use client'

import { useEffect, useRef, useState } from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { AlertCircle, CheckCircle2, Loader2, Play } from 'lucide-react'
import {
  type WebSearchConfig,
  type WebSearchConfigUpdate,
  type WebSearchDefaultEngine,
  type WebSearchEngine,
  type WebSearchTestResponse,
} from '@/lib/api'
import { adminToolsApi } from '@/lib/api/admin'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

const DEFAULT_ENGINES: WebSearchDefaultEngine[] = ['tavily', 'bocha', 'searxng', 'deepseek']
const TEST_ENGINES: WebSearchEngine[] = ['auto', 'tavily', 'bocha', 'searxng', 'deepseek']

type WebSearchConfigApi = Pick<
  typeof adminToolsApi,
  'getWebSearchConfig' | 'updateWebSearchConfig' | 'testWebSearchConfig'
>

interface WebSearchConfigDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSaved?: () => void
  api?: WebSearchConfigApi
}

interface SecretFieldProps {
  id: string
  label: string
  placeholder: string
  value: string
  configured: boolean
  clearRequested: boolean
  missingText?: string
  onChange: (value: string) => void
  onClearRequestedChange: (clear: boolean) => void
}

function SecretField({
  id,
  label,
  placeholder,
  value,
  configured,
  clearRequested,
  missingText,
  onChange,
  onClearRequestedChange,
}: SecretFieldProps) {
  const t = useTranslations('tools.webSearch')
  const hasNewValue = value.trim().length > 0

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <Label htmlFor={id} className="text-xs font-medium">{label}</Label>
        {configured && !hasNewValue && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className={`h-6 px-2 text-xs${clearRequested ? '' : ' text-destructive hover:text-destructive'}`}
            onClick={() => onClearRequestedChange(!clearRequested)}
          >
            {clearRequested ? t('undoClear') : t('clearKey')}
          </Button>
        )}
      </div>
      <Input
        id={id}
        type="password"
        autoComplete="new-password"
        value={value}
        placeholder={placeholder}
        onChange={(event) => {
          onChange(event.target.value)
          if (event.target.value) onClearRequestedChange(false)
        }}
        aria-invalid={clearRequested}
      />
      <p className="text-[11px] text-muted-foreground">
        {hasNewValue
          ? t('newKeyHint')
          : clearRequested
            ? t('willClear')
            : configured
              ? t('keyConfigured')
              : (missingText ?? t('keyMissing'))}
      </p>
    </div>
  )
}

interface ProviderToggleProps {
  label: string
  checked: boolean
  onCheckedChange: (checked: boolean) => void
}

function ProviderToggle({ label, checked, onCheckedChange }: ProviderToggleProps) {
  const t = useTranslations('tools.webSearch')
  return (
    <div className="flex items-center justify-between rounded-md border p-3">
      <div className="space-y-0.5">
        <p className="text-sm font-medium">{label}</p>
        <p className="text-xs text-muted-foreground">{t('providerEnabledHint')}</p>
      </div>
      <Switch
        checked={checked}
        onCheckedChange={onCheckedChange}
        aria-label={`${label} ${t('providerEnabled')}`}
      />
    </div>
  )
}

export function WebSearchConfigDialog({
  open,
  onOpenChange,
  onSaved,
  api = adminToolsApi,
}: WebSearchConfigDialogProps) {
  const t = useTranslations('tools.webSearch')

  const [config, setConfig] = useState<WebSearchConfig | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [defaultEngine, setDefaultEngine] = useState<WebSearchDefaultEngine>('tavily')
  const [tavilyEnabled, setTavilyEnabled] = useState(false)
  const [bochaEnabled, setBochaEnabled] = useState(false)
  const [searxngEnabled, setSearxngEnabled] = useState(false)
  const [deepseekEnabled, setDeepseekEnabled] = useState(false)
  const [searxngBaseUrl, setSearxngBaseUrl] = useState('')
  const [tavilyApiKey, setTavilyApiKey] = useState('')
  const [bochaApiKey, setBochaApiKey] = useState('')
  const [deepseekApiKey, setDeepseekApiKey] = useState('')
  const [searxngAuthToken, setSearxngAuthToken] = useState('')
  const [clearTavilyApiKey, setClearTavilyApiKey] = useState(false)
  const [clearBochaApiKey, setClearBochaApiKey] = useState(false)
  const [clearDeepseekApiKey, setClearDeepseekApiKey] = useState(false)
  const [clearSearxngAuthToken, setClearSearxngAuthToken] = useState(false)

  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const [testQuery, setTestQuery] = useState('')
  const [testEngine, setTestEngine] = useState<WebSearchEngine>('auto')
  const [isTesting, setIsTesting] = useState(false)
  const [testError, setTestError] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<WebSearchTestResponse | null>(null)
  const requestGeneration = useRef(0)

  const applyConfig = (next: WebSearchConfig) => {
    setConfig(next)
    setDefaultEngine(next.default_engine)
    setTavilyEnabled(next.tavily_enabled)
    setBochaEnabled(next.bocha_enabled)
    setSearxngEnabled(next.searxng_enabled)
    setDeepseekEnabled(next.deepseek_enabled)
    setSearxngBaseUrl(next.searxng_base_url)
  }

  useEffect(() => {
    if (!open) return

    let active = true
    const generation = ++requestGeneration.current
    setIsLoading(true)
    setIsSaving(false)
    setIsTesting(false)
    setLoadError(null)
    setSaveError(null)
    setTavilyApiKey('')
    setBochaApiKey('')
    setDeepseekApiKey('')
    setSearxngAuthToken('')
    setClearTavilyApiKey(false)
    setClearBochaApiKey(false)
    setClearDeepseekApiKey(false)
    setClearSearxngAuthToken(false)
    setTestQuery('')
    setTestEngine('auto')
    setTestError(null)
    setTestResult(null)

    api.getWebSearchConfig()
      .then((next) => {
        if (active && generation === requestGeneration.current) applyConfig(next)
      })
      .catch((error: unknown) => {
        if (!active || generation !== requestGeneration.current) return
        setLoadError(error instanceof Error && error.message ? error.message : t('loadFailed'))
      })
      .finally(() => {
        if (active && generation === requestGeneration.current) setIsLoading(false)
      })

    return () => {
      active = false
    }
    // applyConfig is intentionally excluded: it only mirrors the fetched config.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, api])

  const isEngineEnabled = (engine: WebSearchDefaultEngine): boolean => {
    if (engine === 'tavily') return tavilyEnabled
    if (engine === 'bocha') return bochaEnabled
    if (engine === 'deepseek') return deepseekEnabled
    return searxngEnabled
  }

  const handleSave = async () => {
    setSaveError(null)

    const anyProviderEnabled = tavilyEnabled || bochaEnabled || searxngEnabled || deepseekEnabled
    if (anyProviderEnabled && !isEngineEnabled(defaultEngine)) {
      setSaveError(t('defaultEngineDisabled'))
      return
    }
    if (searxngEnabled && !searxngBaseUrl.trim()) {
      setSaveError(t('searxngBaseUrlRequired'))
      return
    }

    const searxngUrlChanged =
      searxngBaseUrl.trim().replace(/\/+$/, '')
      !== (config?.searxng_base_url ?? '').trim().replace(/\/+$/, '')
    if (
      searxngUrlChanged
      && config?.searxng_auth_token_configured
      && !searxngAuthToken.trim()
      && !clearSearxngAuthToken
    ) {
      setSaveError(t('searxngTokenConfirmationRequired'))
      return
    }

    const payload: WebSearchConfigUpdate = {
      default_engine: defaultEngine,
      tavily_enabled: tavilyEnabled,
      bocha_enabled: bochaEnabled,
      searxng_enabled: searxngEnabled,
      deepseek_enabled: deepseekEnabled,
      searxng_base_url: searxngBaseUrl.trim(),
    }

    if (tavilyApiKey.trim()) payload.tavily_api_key = tavilyApiKey.trim()
    else if (clearTavilyApiKey) payload.tavily_api_key = ''
    if (bochaApiKey.trim()) payload.bocha_api_key = bochaApiKey.trim()
    else if (clearBochaApiKey) payload.bocha_api_key = ''
    if (deepseekApiKey.trim()) payload.deepseek_api_key = deepseekApiKey.trim()
    else if (clearDeepseekApiKey) payload.deepseek_api_key = ''
    if (searxngAuthToken.trim()) payload.searxng_auth_token = searxngAuthToken.trim()
    else if (clearSearxngAuthToken) payload.searxng_auth_token = ''

    setIsSaving(true)
    const generation = requestGeneration.current
    try {
      const updated = await api.updateWebSearchConfig(payload)
      if (generation !== requestGeneration.current) return
      applyConfig(updated)
      setTavilyApiKey('')
      setBochaApiKey('')
      setDeepseekApiKey('')
      setSearxngAuthToken('')
      setClearTavilyApiKey(false)
      setClearBochaApiKey(false)
      setClearDeepseekApiKey(false)
      setClearSearxngAuthToken(false)
      toast.success(t('saved'))
      onSaved?.()
    } catch (error: unknown) {
      if (generation !== requestGeneration.current) return
      setSaveError(error instanceof Error && error.message ? error.message : t('saveFailed'))
    } finally {
      if (generation === requestGeneration.current) setIsSaving(false)
    }
  }

  const handleTest = async () => {
    const query = testQuery.trim()
    if (!query) {
      setTestError(t('testQueryRequired'))
      return
    }

    setIsTesting(true)
    setTestError(null)
    setTestResult(null)
    const generation = requestGeneration.current
    try {
      const result = await api.testWebSearchConfig({ query, engine: testEngine })
      if (generation !== requestGeneration.current) return
      setTestResult(result)
    } catch (error: unknown) {
      if (generation !== requestGeneration.current) return
      setTestError(error instanceof Error && error.message ? error.message : t('testFailed'))
    } finally {
      if (generation === requestGeneration.current) setIsTesting(false)
    }
  }

  const engineLabel = (engine: WebSearchEngine): string => {
    if (engine === 'auto') return t('engineAuto')
    if (engine === 'tavily') return t('engineTavily')
    if (engine === 'bocha') return t('engineBocha')
    if (engine === 'deepseek') return t('engineDeepseek')
    return t('engineSearxng')
  }

  const handleOpenChange = (next: boolean) => {
    if (!next) requestGeneration.current += 1
    onOpenChange(next)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('title')}</DialogTitle>
          <DialogDescription>{t('description')}</DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : loadError ? (
          <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive" role="alert">
            {loadError}
          </div>
        ) : (
          <div className="space-y-5 py-2">
            {config?.legacy_credentials_present && (
              <div className="flex items-start gap-2 rounded-md border border-amber-300/60 bg-amber-50 p-3 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-400">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{t('legacyWarning')}</span>
              </div>
            )}

            <div className="space-y-1.5">
              <Label htmlFor="web-search-default-engine" className="text-xs font-medium">
                {t('defaultEngine')}
              </Label>
              <Select
                value={defaultEngine}
                onValueChange={(value) => setDefaultEngine(value as WebSearchDefaultEngine)}
              >
                <SelectTrigger id="web-search-default-engine" className="w-full">
                  <SelectValue>{engineLabel(defaultEngine)}</SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {DEFAULT_ENGINES.map((engine) => (
                    <SelectItem
                      key={engine}
                      value={engine}
                      disabled={(tavilyEnabled || bochaEnabled) && !isEngineEnabled(engine)}
                    >
                      {engineLabel(engine)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-[11px] text-muted-foreground">{t('defaultEngineHint')}</p>
            </div>

            <div className="space-y-3">
              <ProviderToggle
                label={t('tavily')}
                checked={tavilyEnabled}
                onCheckedChange={setTavilyEnabled}
              />
              <SecretField
                id="web-search-tavily-api-key"
                label={t('tavilyApiKey')}
                placeholder={t('tavilyKeyPlaceholder')}
                value={tavilyApiKey}
                configured={Boolean(config?.tavily_api_key_configured)}
                clearRequested={clearTavilyApiKey}
                onChange={setTavilyApiKey}
                onClearRequestedChange={setClearTavilyApiKey}
              />

              <ProviderToggle
                label={t('bocha')}
                checked={bochaEnabled}
                onCheckedChange={setBochaEnabled}
              />
              <SecretField
                id="web-search-bocha-api-key"
                label={t('bochaApiKey')}
                placeholder={t('bochaKeyPlaceholder')}
                value={bochaApiKey}
                configured={Boolean(config?.bocha_api_key_configured)}
                clearRequested={clearBochaApiKey}
                onChange={setBochaApiKey}
                onClearRequestedChange={setClearBochaApiKey}
              />

              <ProviderToggle
                label={t('deepseek')}
                checked={deepseekEnabled}
                onCheckedChange={setDeepseekEnabled}
              />
              <SecretField
                id="web-search-deepseek-api-key"
                label={t('deepseekApiKey')}
                placeholder={t('deepseekKeyPlaceholder')}
                value={deepseekApiKey}
                configured={Boolean(config?.deepseek_api_key_configured)}
                clearRequested={clearDeepseekApiKey}
                onChange={setDeepseekApiKey}
                onClearRequestedChange={setClearDeepseekApiKey}
              />
              <p className="text-[11px] text-muted-foreground">{t('deepseekKeyHint')}</p>

              <ProviderToggle
                label={t('searxng')}
                checked={searxngEnabled}
                onCheckedChange={setSearxngEnabled}
              />
              <div className="space-y-1.5">
                <Label htmlFor="web-search-searxng-base-url" className="text-xs font-medium">
                  {t('searxngBaseUrl')}
                </Label>
                <Input
                  id="web-search-searxng-base-url"
                  type="text"
                  inputMode="url"
                  value={searxngBaseUrl}
                  placeholder={t('searxngBaseUrlPlaceholder')}
                  onChange={(event) => setSearxngBaseUrl(event.target.value)}
                  aria-invalid={searxngEnabled && !searxngBaseUrl.trim()}
                />
                <p className="text-[11px] text-muted-foreground">{t('searxngBaseUrlHint')}</p>
              </div>
              <SecretField
                id="web-search-searxng-auth-token"
                label={t('searxngAuthToken')}
                placeholder={t('searxngAuthTokenPlaceholder')}
                value={searxngAuthToken}
                configured={Boolean(config?.searxng_auth_token_configured)}
                clearRequested={clearSearxngAuthToken}
                missingText={t('searxngTokenOptional')}
                onChange={setSearxngAuthToken}
                onClearRequestedChange={setClearSearxngAuthToken}
              />
              <p className="text-[11px] text-muted-foreground">{t('searxngTokenHttpsHint')}</p>
              {config?.searxng_auth_token_configured && (
                <p className="text-[11px] text-muted-foreground">{t('searxngUrlChangeHint')}</p>
              )}
            </div>

            {saveError && (
              <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive" role="alert">
                {saveError}
              </div>
            )}

            <div className="space-y-3 rounded-md border p-3">
              <div>
                <p className="text-sm font-medium">{t('testTitle')}</p>
                <p className="text-xs text-muted-foreground">{t('testDescription')}</p>
              </div>
              <div className="flex flex-col gap-2 sm:flex-row">
                <Input
                  value={testQuery}
                  onChange={(event) => setTestQuery(event.target.value)}
                  placeholder={t('testQueryPlaceholder')}
                  aria-label={t('testQuery')}
                  className="flex-1"
                />
                <Select
                  value={testEngine}
                  onValueChange={(value) => setTestEngine(value as WebSearchEngine)}
                >
                  <SelectTrigger className="sm:w-40" aria-label={t('testEngine')}>
                    <SelectValue>{engineLabel(testEngine)}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {TEST_ENGINES.map((engine) => (
                      <SelectItem
                        key={engine}
                        value={engine}
                        disabled={engine !== 'auto' && !isEngineEnabled(engine)}
                      >
                        {engineLabel(engine)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleTest}
                  disabled={isTesting}
                >
                  {isTesting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                  {isTesting ? t('testing') : t('runTest')}
                </Button>
              </div>

              {testError && (
                <p className="text-sm text-destructive" role="alert">{testError}</p>
              )}

              {testResult && (
                <div className="space-y-2" data-testid="web-search-test-result">
                  {testResult.success ? (
                    <p className="flex items-center gap-1.5 text-xs text-emerald-600 dark:text-emerald-400">
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      {t('testSucceeded')}
                      {testResult.search_engine ? ` · ${engineLabel(testResult.search_engine)}` : ''}
                    </p>
                  ) : (
                    <p className="flex items-start gap-1.5 text-xs text-destructive" role="alert">
                      <AlertCircle className="mt-0.5 h-3.5 w-3.5" />
                      {testResult.error || t('testFailed')}
                    </p>
                  )}
                  {testResult.success && testResult.results?.length ? (
                    <ul className="space-y-2">
                      {testResult.results.map((item, index) => (
                        <li key={`${item.url}-${index}`} className="rounded-md border p-2">
                          <a
                            href={item.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-sm font-medium text-primary hover:underline break-all"
                          >
                            {item.title || item.url}
                          </a>
                          <p className="mt-0.5 text-[11px] text-muted-foreground break-all">{item.url}</p>
                          {item.content && (
                            <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{item.content}</p>
                          )}
                        </li>
                      ))}
                    </ul>
                  ) : testResult.success ? (
                    <p className="text-xs text-muted-foreground">{t('testNoResults')}</p>
                  ) : null}
                </div>
              )}
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)}>
            {t('cancel')}
          </Button>
          <Button onClick={handleSave} disabled={isLoading || isSaving || !!loadError}>
            {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default WebSearchConfigDialog
