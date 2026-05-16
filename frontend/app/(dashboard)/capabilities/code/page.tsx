'use client'

import { useState, useEffect, useRef, useCallback, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import {
  ArrowLeft,
  Save,
  Play,
  Loader2,
  FileCode,
  ChevronDown,
  ChevronRight,
  X,
  Plus,
  Trash2,
} from 'lucide-react'
import { RoutePermissionGuard } from '@/components/auth/permission-guard'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { cn } from '@/lib/utils'
import { formatValidationSummaryMessage } from '@/lib/validation'
import { toast } from 'sonner'
import { ToolCreateInput, ToolUpdateInput, CodeConfig, ToolParameter, ToolCategory, SandboxArtifactConfig, SandboxLimitsConfig } from '@/lib/api/tools'
import { ApiError } from '@/lib/api'
import { adminToolsApi, teamsApi as adminTeamsApi, type Team } from '@/lib/api/admin'
import { ImageUpload } from '@/components/ui/image-upload'
import { ToolCategoryInput } from '@/app/(platform)/app/capabilities/_components/tool-category-input'
import { useCanPerform } from '@/components/permission-guard'
import Editor from '@monaco-editor/react'

const CODE_LANGUAGES = [
  { value: 'javascript', label: 'JavaScript' },
  { value: 'python', label: 'Python' },
] as const

type CodeLanguage = (typeof CODE_LANGUAGES)[number]['value']

const DEFAULT_CODE: Record<CodeLanguage, string> = {
  javascript: `// JavaScript Tool
// Available: params (object with input parameters)
// Return: result as string or object

async function execute(params) {
  const { input } = params;
  
  // Your code here
  const result = \`Processed: \${input}\`;
  
  return result;
}

// Execute and return result
return execute(params);
`,
  python: `# Python Tool
# Available: params (dict with input parameters)
# Return: result as string or dict

def execute(params):
    input_value = params.get('input', '')
    
    # Your code here
    result = f"Processed: {input_value}"
    
    return result

# Execute and return result
return execute(params)
`,
}

const PARAM_TYPES = [
  { value: 'string', label: 'String' },
  { value: 'number', label: 'Number' },
  { value: 'integer', label: 'Integer' },
  { value: 'boolean', label: 'Boolean' },
  { value: 'array', label: 'Array' },
  { value: 'object', label: 'Object' },
] as const

const DEFAULT_PARAM: ToolParameter = {
  name: '',
  type: 'string',
  description: '',
  required: false,
}

const PYTHON_PACKAGE_PATTERN = /^[A-Za-z0-9_.-]+==[^=].+$/
const JS_PACKAGE_PATTERN = /^[^\s@][^\s]*@[^\s].+$/

const normalizePackageSourceUrl = (value: string): string => value.trim().replace(/\/+$/, '')

const isValidPackageSourceUrl = (value: string): boolean => {
  try {
    const url = new URL(value)
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password
  } catch {
    return false
  }
}

const parseRuntimeLines = (value: string): string[] =>
  value
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)

const findInvalidRuntimeValue = (values: string[], pattern: RegExp): string | null =>
  values.find((value) => !pattern.test(value)) || null

const DEFAULT_LIMITS: SandboxLimitsConfig = {
  timeout_seconds: 30,
  disk_mb: 1024,
  max_stdout_kb: 256,
  max_stderr_kb: 256,
}

const parsePositiveNumber = (value: string, fallback: number): number => {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback
}

const parseArtifactConfig = (artifacts: SandboxArtifactConfig[]): SandboxArtifactConfig[] =>
  artifacts
    .map((artifact) => ({
      path: artifact.path.trim(),
      optional: artifact.optional,
      description: artifact.description?.trim() || undefined,
    }))
    .filter((artifact) => artifact.path)

const TOOL_NAME_PATTERN = /^[A-Za-z][A-Za-z0-9_]*$/

const joinFieldErrorMessages = (fieldErrors: Record<string, string>): string => {
  const messages = Object.values(fieldErrors).filter(Boolean)
  return Array.from(new Set(messages)).join(', ')
}

const clearFieldError = (fieldErrors: Record<string, string>, field: string): Record<string, string> => {
  if (!fieldErrors[field]) {
    return fieldErrors
  }

  const next = { ...fieldErrors }
  delete next[field]
  return next
}

const INLINE_ERROR_FIELDS = new Set([
  'name',
  'display_name',
  'description',
  'params',
  'code_config.python_packages',
  'code_config.js_packages',
  'code_config.python_package_index_url',
  'code_config.node_package_registry_url',
  'code_config.command',
  'code_config.limits.timeout_seconds',
  'code_config.limits.disk_mb',
  'code_config.limits.max_stdout_kb',
  'code_config.limits.max_stderr_kb',
])

const shouldShowSummaryFieldError = (field: string): boolean => {
  if (INLINE_ERROR_FIELDS.has(field)) {
    return false
  }

  return !/^code_config\.artifacts\.\d+\.(path|description)$/.test(field)
}

const getSummaryFieldLabel = (
  t: ReturnType<typeof useTranslations<'tools'>>,
  field: string
): string | undefined => {
  if (field === 'display_name') return t('displayName')
  if (field === 'description') return t('descriptionLabel')
  if (field === 'code_config.command') return t('codeEditor.command')
  if (field === 'code_config.python_packages') return t('codeEditor.pythonPackages')
  if (field === 'code_config.js_packages') return t('codeEditor.jsPackages')
  if (field === 'code_config.python_package_index_url') return t('codeEditor.pythonPackageIndexUrl')
  if (field === 'code_config.node_package_registry_url') return t('codeEditor.nodePackageRegistryUrl')
  if (field === 'code_config.limits.timeout_seconds') return t('codeEditor.timeoutSeconds')
  if (field === 'code_config.limits.disk_mb') return t('codeEditor.diskMb')
  if (field === 'code_config.limits.max_stdout_kb') return t('codeEditor.maxStdoutKb')
  if (field === 'code_config.limits.max_stderr_kb') return t('codeEditor.maxStderrKb')
  if (field.startsWith('code_config.artifacts.')) return t('codeEditor.artifacts')
  if (field.startsWith('parameters.') || field === 'params') return t('codeEditor.parameters')
  return undefined
}

function CodeToolPageContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const toolId = searchParams.get('id')
  const teamIdParam = searchParams.get('teamId')
  const t = useTranslations('tools')
  const tCommon = useTranslations('common')
  const { canPerform } = useCanPerform()
  const canSave = canPerform(toolId ? 'admin:capability:update' : 'admin:capability:create')
  const canExecute = canPerform('admin:capability:execute')

  // 团队信息
  const [teams, setTeams] = useState<Team[]>([])
  const [currentTeamId, setCurrentTeamId] = useState<string>(teamIdParam || '')

  // 工具信息
  const [name, setName] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [description, setDescription] = useState('')
  const [icon, setIcon] = useState('')
  const [category, setCategory] = useState<ToolCategory>('code')
  const [isEnabled, setIsEnabled] = useState(true)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  // 参数定义
  const [parameters, setParameters] = useState<ToolParameter[]>([
    { name: 'input', type: 'string', description: '输入内容', required: true },
  ])

  // 代码配置
  const [language, setLanguage] = useState<CodeLanguage>('javascript')
  const [code, setCode] = useState(DEFAULT_CODE.javascript)
  const [pythonPackagesText, setPythonPackagesText] = useState('')
  const [jsPackagesText, setJsPackagesText] = useState('')
  const [pythonPackageIndexUrl, setPythonPackageIndexUrl] = useState('')
  const [nodePackageRegistryUrl, setNodePackageRegistryUrl] = useState('')
  const [commandText, setCommandText] = useState('')
  const [timeoutSeconds, setTimeoutSeconds] = useState(String(DEFAULT_LIMITS.timeout_seconds))
  const [diskMb, setDiskMb] = useState(String(DEFAULT_LIMITS.disk_mb))
  const [maxStdoutKb, setMaxStdoutKb] = useState(String(DEFAULT_LIMITS.max_stdout_kb))
  const [maxStderrKb, setMaxStderrKb] = useState(String(DEFAULT_LIMITS.max_stderr_kb))
  const [artifacts, setArtifacts] = useState<SandboxArtifactConfig[]>([])
  const isCodeModified = useRef(false)

  // 测试
  const [testInput, setTestInput] = useState('{\n  "input": "test"\n}')
  const [testOutput, setTestOutput] = useState('')
  const [isRunning, setIsRunning] = useState(false)

  // UI 状态
  const [isLoading, setIsLoading] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(true)
  const [paramsOpen, setParamsOpen] = useState(true)
  const [testOpen, setTestOpen] = useState(true)
  const [outputOpen, setOutputOpen] = useState(false)

  const isEditing = !!toolId

  // 加载团队列表
  useEffect(() => {
    const loadTeams = async () => {
      try {
        const data = await adminTeamsApi.getTeams(1, 100)
        setTeams(data.items)
        if (data.items.length > 0 && !currentTeamId) {
          setCurrentTeamId(data.items[0].id)
        }
      } catch {
        // 忽略错误
      }
    }
    loadTeams()
  }, [currentTeamId])

  const loadTool = useCallback(async (id: string) => {
    setIsLoading(true)
    try {
      const tool = await adminToolsApi.getById(id)
      setName(tool.name)
      setDisplayName(tool.display_name)
      setDescription(tool.description)
      setIcon(tool.icon || '')
      setCategory(tool.category || 'code')
      setIsEnabled(tool.is_enabled)
      setFieldErrors({})

      // 加载参数
      if (tool.parameters && tool.parameters.length > 0) {
        setParameters(tool.parameters)
      }

      if (tool.code_config) {
        const loadedCode = tool.code_config.code || DEFAULT_CODE[tool.code_config.language as CodeLanguage]
        setLanguage(tool.code_config.language as CodeLanguage)
        setCode(loadedCode)
        setPythonPackagesText((tool.code_config.python_packages || []).join('\n'))
        setJsPackagesText((tool.code_config.js_packages || []).join('\n'))
        setPythonPackageIndexUrl(tool.code_config.python_package_index_url || '')
        setNodePackageRegistryUrl(tool.code_config.node_package_registry_url || '')
        setCommandText((tool.code_config.command || []).join('\n'))
        setTimeoutSeconds(String(tool.code_config.limits?.timeout_seconds ?? DEFAULT_LIMITS.timeout_seconds))
        setDiskMb(String(tool.code_config.limits?.disk_mb ?? DEFAULT_LIMITS.disk_mb))
        setMaxStdoutKb(String(tool.code_config.limits?.max_stdout_kb ?? DEFAULT_LIMITS.max_stdout_kb))
        setMaxStderrKb(String(tool.code_config.limits?.max_stderr_kb ?? DEFAULT_LIMITS.max_stderr_kb))
        setArtifacts(tool.code_config.artifacts || [])
        // 加载的代码如果不是默认代码，标记为已修改
        isCodeModified.current = loadedCode.trim() !== DEFAULT_CODE[tool.code_config.language as CodeLanguage].trim()
      }
    } catch {
      // toast handled by API interceptor
      router.push('/capabilities')
    } finally {
      setIsLoading(false)
    }
  }, [router])

  useEffect(() => {
    if (toolId) {
      loadTool(toolId)
    }
  }, [toolId, loadTool])

  // 参数管理
  const addParameter = () => {
    setParameters([...parameters, { ...DEFAULT_PARAM, name: `param${parameters.length + 1}` }])
  }

  const removeParameter = (index: number) => {
    setParameters(parameters.filter((_, i) => i !== index))
  }

  const updateParameter = (index: number, field: keyof ToolParameter, value: unknown) => {
    const updated = [...parameters]
    updated[index] = { ...updated[index], [field]: value }
    setParameters(updated)
  }

  // 根据参数生成测试输入模板
  const generateTestInput = () => {
    const template: Record<string, unknown> = {}
    parameters.forEach((param) => {
      switch (param.type) {
        case 'string':
          template[param.name] = param.default ?? 'test'
          break
        case 'number':
        case 'integer':
          template[param.name] = param.default ?? 0
          break
        case 'boolean':
          template[param.name] = param.default ?? false
          break
        case 'array':
          template[param.name] = param.default ?? []
          break
        case 'object':
          template[param.name] = param.default ?? {}
          break
        default:
          template[param.name] = param.default ?? null
      }
    })
    setTestInput(JSON.stringify(template, null, 2))
  }

  const handleLanguageChange = (newLanguage: CodeLanguage) => {
    // 如果用户没有修改过代码，切换到新语言的示例
    if (!isCodeModified.current) {
      setCode(DEFAULT_CODE[newLanguage])
    }
    setLanguage(newLanguage)
  }

  const handleCodeChange = (value: string | undefined) => {
    const newCode = value || ''
    setCode(newCode)
    // 标记用户已修改代码（除非清空或恢复为当前语言的默认代码）
    isCodeModified.current = newCode.trim() !== '' && newCode.trim() !== DEFAULT_CODE[language].trim()
  }

  const addArtifact = () => {
    setArtifacts([...artifacts, { path: '', optional: false, description: '' }])
  }

  const removeArtifact = (index: number) => {
    setArtifacts(artifacts.filter((_, i) => i !== index))
  }

  const updateArtifact = (index: number, field: keyof SandboxArtifactConfig, value: unknown) => {
    const updated = [...artifacts]
    updated[index] = { ...updated[index], [field]: value }
    setArtifacts(updated)
  }

  const buildRuntimeConfig = () => {
    const pythonPackages = parseRuntimeLines(pythonPackagesText)
    const jsPackages = parseRuntimeLines(jsPackagesText)
    const normalizedPythonPackageIndexUrl = normalizePackageSourceUrl(pythonPackageIndexUrl)
    const normalizedNodePackageRegistryUrl = normalizePackageSourceUrl(nodePackageRegistryUrl)
    const command = parseRuntimeLines(commandText)
    const parsedArtifacts = parseArtifactConfig(artifacts)

    const invalidPythonPackage = findInvalidRuntimeValue(pythonPackages, PYTHON_PACKAGE_PATTERN)
    if (invalidPythonPackage) {
      return { error: t('codeEditor.invalidPythonPackage', { value: invalidPythonPackage }) }
    }

    const invalidJsPackage = findInvalidRuntimeValue(jsPackages, JS_PACKAGE_PATTERN)
    if (invalidJsPackage) {
      return { error: t('codeEditor.invalidJsPackage', { value: invalidJsPackage }) }
    }

    const invalidArtifact = parsedArtifacts.find((artifact) => !artifact.path.startsWith('/workspace'))
    if (invalidArtifact) {
      return { error: t('codeEditor.invalidArtifactPath', { value: invalidArtifact.path }) }
    }

    if (normalizedPythonPackageIndexUrl && !isValidPackageSourceUrl(normalizedPythonPackageIndexUrl)) {
      return { error: t('codeEditor.invalidPackageSourceUrl', { value: normalizedPythonPackageIndexUrl }) }
    }

    if (normalizedNodePackageRegistryUrl && !isValidPackageSourceUrl(normalizedNodePackageRegistryUrl)) {
      return { error: t('codeEditor.invalidPackageSourceUrl', { value: normalizedNodePackageRegistryUrl }) }
    }

    const limits: SandboxLimitsConfig = {
      timeout_seconds: parsePositiveNumber(timeoutSeconds, DEFAULT_LIMITS.timeout_seconds ?? 30),
      disk_mb: parsePositiveNumber(diskMb, DEFAULT_LIMITS.disk_mb ?? 1024),
      max_stdout_kb: parsePositiveNumber(maxStdoutKb, DEFAULT_LIMITS.max_stdout_kb ?? 256),
      max_stderr_kb: parsePositiveNumber(maxStderrKb, DEFAULT_LIMITS.max_stderr_kb ?? 256),
    }

    return {
      pythonPackages,
      jsPackages,
      pythonPackageIndexUrl: normalizedPythonPackageIndexUrl || undefined,
      nodePackageRegistryUrl: normalizedNodePackageRegistryUrl || undefined,
      command,
      limits,
      artifacts: parsedArtifacts,
    }
  }

  const handleSave = async () => {
    if (!name.trim()) {
      setFieldErrors({ name: t('error.nameRequired') })
      toast.error(t('error.nameRequired'))
      return
    }

    if (!TOOL_NAME_PATTERN.test(name.trim())) {
      setFieldErrors({ name: t('error.invalidName') })
      return
    }

    setFieldErrors({})

    if (!currentTeamId) {
      toast.error(t('error.noTeamSelected'))
      return
    }

    // 验证参数
    const validParams = parameters.filter((p) => p.name.trim())
    const paramNames = validParams.map((p) => p.name)
    if (new Set(paramNames).size !== paramNames.length) {
      toast.error(t('error.duplicateParamName'))
      return
    }

    setIsSaving(true)
    try {
      const runtime = buildRuntimeConfig()
      if ('error' in runtime) {
        toast.error(runtime.error)
        return
      }

      const codeConfig: CodeConfig = {
        language,
        code,
        python_packages: runtime.pythonPackages,
        js_packages: runtime.jsPackages,
        python_package_index_url: runtime.pythonPackageIndexUrl,
        node_package_registry_url: runtime.nodePackageRegistryUrl,
        command: runtime.command,
        artifacts: runtime.artifacts,
        limits: runtime.limits,
      }

      const data: ToolCreateInput | ToolUpdateInput = {
        name,
        display_name: displayName || name,
        description: description.trim() || t('codeEditor.defaultDescription'),
        icon,
        category,
        is_enabled: isEnabled,
        type: 'custom',
        custom_type: 'code',
        parameters: validParams,
        code_config: codeConfig,
      }

      if (isEditing && toolId) {
        await adminToolsApi.update(toolId, data)
        toast.success(t('success.updated'))
      } else {
        await adminToolsApi.create(currentTeamId, data as ToolCreateInput)
        toast.success(t('success.created'))
        router.push('/capabilities')
      }
    } catch (error) {
      if (error instanceof ApiError && error.isValidationError()) {
        const nextFieldErrors = error.getFieldErrors()
        setFieldErrors(nextFieldErrors)
        toast.error(joinFieldErrorMessages(nextFieldErrors) || error.message)
      }
      // other errors are handled by the API interceptor
    } finally {
      setIsSaving(false)
    }
  }

  const handleRun = async () => {
    setIsRunning(true)
    setTestOutput('')
    setOutputOpen(true)
    setFieldErrors((current) => ({
      ...Object.fromEntries(
        Object.entries(current).filter(([field]) => !field.startsWith('params'))
      ),
    }))

    try {
      let params: Record<string, unknown>
      try {
        params = JSON.parse(testInput)
      } catch {
        setTestOutput(`${t('codeEditor.errorLabel')}: ${t('codeEditor.invalidJsonInput')}`)
        setIsRunning(false)
        return
      }

      const runtime = buildRuntimeConfig()
      if ('error' in runtime) {
        setTestOutput(`${t('codeEditor.errorLabel')}: ${runtime.error}`)
        setIsRunning(false)
        return
      }

      const requestTimeoutSeconds = runtime.limits.timeout_seconds ?? 30
      const result = await adminToolsApi.executeCode({
        language,
        code,
        params,
        timeout: requestTimeoutSeconds,
        client_timeout_ms: Math.max(requestTimeoutSeconds * 1000 + 30000, 120000),
        python_packages: runtime.pythonPackages,
        js_packages: runtime.jsPackages,
        python_package_index_url: runtime.pythonPackageIndexUrl,
        node_package_registry_url: runtime.nodePackageRegistryUrl,
        command: runtime.command,
        artifacts: runtime.artifacts,
        limits: runtime.limits,
      })

      let output = ''
      if (result.logs) {
        output += `${t('codeEditor.logsLabel')}:\n${result.logs}\n\n`
      }
      if (result.success) {
        const resultStr =
          typeof result.result === 'string'
            ? result.result
            : JSON.stringify(result.result, null, 2)
        output += `${t('codeEditor.resultLabel')}:\n${resultStr}`
      } else {
        output += `${t('codeEditor.errorLabel')}:\n${result.error || t('codeEditor.executionFailed')}`
      }
      if (result.artifacts?.length) {
        output += `\n\n${t('codeEditor.artifactsLabel')}:\n${JSON.stringify(result.artifacts, null, 2)}`
      }
      if (result.duration_ms !== undefined) {
        output += `\n\n${t('codeEditor.durationLabel')}: ${result.duration_ms}ms`
      }
      setTestOutput(output)
    } catch (error: unknown) {
      if (error instanceof ApiError && error.isValidationError()) {
        const nextFieldErrors = Object.fromEntries(
          Object.entries(error.getFieldErrors()).map(([field, message]) => {
            if (field === 'params') {
              return ['params', message]
            }
            if (field === 'command') {
              return ['code_config.command', message]
            }
            if (field.startsWith('limits.')) {
              return [`code_config.${field}`, message]
            }
            return [field, message]
          })
        )
        setFieldErrors((current) => ({
          ...Object.fromEntries(
            Object.entries(current).filter(([field]) => !field.startsWith('params'))
          ),
          ...nextFieldErrors,
        }))
      } else {
        const message = error instanceof Error ? error.message : t('codeEditor.executionFailed')
        setTestOutput(`${t('codeEditor.errorLabel')}: ${message}`)
      }
    } finally {
      setIsRunning(false)
    }
  }

  const handleBack = () => {
    router.push('/capabilities')
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="h-[calc(100vh-56px)] flex flex-col px-8 pb-4 overflow-hidden">
      {/* Header - 固定高度 */}
      <header className="h-14 shrink-0 flex items-center justify-between border-b bg-background z-10">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={handleBack}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <span className="text-xl">{icon}</span>
          <div>
            <h1 className="text-sm font-semibold leading-tight">
              {isEditing ? displayName || name : t('codeEditor.newTitle')}
            </h1>
            <p className="text-xs text-muted-foreground">{t('codeEditor.subtitle')}</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* 团队选择 (仅创建时显示) */}
          {!isEditing && teams.length > 1 && (
            <Select value={currentTeamId} onValueChange={(v) => v && setCurrentTeamId(v)}>
              <SelectTrigger size="sm" className="w-32">
                <SelectValue>
                  {teams.find((team) => team.id === currentTeamId)?.name || t('selectTeam')}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {teams.map((team) => (
                  <SelectItem key={team.id} value={team.id}>
                    {team.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}

          <Select value={language} onValueChange={(v) => handleLanguageChange(v as CodeLanguage)}>
            <SelectTrigger size="sm" className="w-28">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {CODE_LANGUAGES.map((lang) => (
                <SelectItem key={lang.value} value={lang.value}>
                  {lang.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {canExecute && (
            <Button variant="outline" size="sm" onClick={handleRun} disabled={isRunning || !code.trim()}>
              {isRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              <span className="ml-1.5">{t('codeEditor.run')}</span>
            </Button>
          )}

          {canSave && (
            <Button size="sm" onClick={handleSave} disabled={isSaving}>
              {isSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              <span className="ml-1.5">{tCommon('save')}</span>
            </Button>
          )}
        </div>
      </header>

      {/* Main - 相对定位容器 */}
      <div className="flex-1 relative">
        {/* 左侧：编辑器区域 - 绝对定位 */}
        <div className="absolute top-0 left-0 bottom-0 right-80 flex flex-col border-r">
          {/* 文件标签 */}
          <div className="h-10 shrink-0 flex items-center gap-2 px-4 border-b bg-muted/30">
            <FileCode className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-medium">
              {name || 'untitled'}.{language === 'javascript' ? 'js' : 'py'}
            </span>
            <Badge variant="secondary" className="text-xs">
              {CODE_LANGUAGES.find((l) => l.value === language)?.label}
            </Badge>
          </div>
          {/* Monaco Editor */}
          <div className="flex-1 overflow-hidden">
            <Editor
              height="100%"
              language={language}
              value={code}
              onChange={handleCodeChange}
              theme="vs-dark"
              options={{
                minimap: { enabled: false },
                fontSize: 14,
                lineNumbers: 'on',
                scrollBeyondLastLine: false,
                automaticLayout: true,
                tabSize: 2,
                wordWrap: 'on',
                padding: { top: 16 },
              }}
            />
          </div>
        </div>

        {/* 右侧：配置面板 - 绝对定位，独立滚动 */}
        <aside className="absolute top-0 right-0 bottom-0 w-80 overflow-y-auto bg-muted/10">
          <div className="p-4 space-y-1">
            {Object.entries(fieldErrors).some(([field]) => shouldShowSummaryFieldError(field)) && (
              <div className="mb-4 space-y-1 rounded-md border border-destructive/30 bg-destructive/5 p-3">
                {Object.entries(fieldErrors)
                  .filter(([field]) => shouldShowSummaryFieldError(field))
                  .map(([field, message]) => (
                    <p key={field} className="text-xs text-destructive">
                      {formatValidationSummaryMessage(field, message, { [field]: getSummaryFieldLabel(t, field) ?? '' })}
                    </p>
                  ))}
              </div>
            )}
            {/* 基本信息 */}
            <Collapsible open={settingsOpen} onOpenChange={setSettingsOpen}>
              <CollapsibleTrigger className="flex items-center gap-2 w-full py-2 text-sm font-medium hover:text-foreground/80">
                {settingsOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                {t('codeEditor.basicInfo')}
              </CollapsibleTrigger>
              <CollapsibleContent className="space-y-3 pt-2 pb-4">
                <div className="space-y-1.5">
                  <Label htmlFor="name" className="text-xs text-muted-foreground">
                    {t('name')}
                  </Label>
                  <Input
                    id="name"
                    placeholder="my_tool"
                    value={name}
                    onChange={(e) => {
                      setName(e.target.value)
                      setFieldErrors((current) => clearFieldError(current, 'name'))
                    }}
                    disabled={isEditing}
                    className="h-8 text-sm"
                    aria-invalid={!!fieldErrors.name}
                  />
                  {fieldErrors.name && <p className="text-xs text-destructive">{fieldErrors.name}</p>}
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="displayName" className="text-xs text-muted-foreground">
                    {t('displayName')}
                  </Label>
                  <Input
                    id="displayName"
                    placeholder="My Tool"
                    value={displayName}
                    onChange={(e) => {
                      setDisplayName(e.target.value)
                      setFieldErrors((current) => clearFieldError(current, 'display_name'))
                    }}
                    className="h-8 text-sm"
                    aria-invalid={!!fieldErrors.display_name}
                  />
                  {fieldErrors.display_name && <p className="text-xs text-destructive">{fieldErrors.display_name}</p>}
                </div>
                <div className="flex gap-2">
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">
                      {t('icon')}
                    </Label>
                    <ImageUpload
                      value={icon.startsWith('http') ? icon : ''}
                      onChange={setIcon}
                      previewSize="sm"
                      category="icons"
                      placeholder={
                        <span className="text-xl">
                          {icon.startsWith('http') ? '' : icon}
                        </span>
                      }
                    />
                  </div>
                  <div className="flex-1 space-y-1.5">
                    <Label htmlFor="category" className="text-xs text-muted-foreground">
                      {t('category')}
                    </Label>
                    <ToolCategoryInput
                      value={category}
                      onChange={setCategory}
                      inputClassName="h-8 text-sm"
                    />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="description" className="text-xs text-muted-foreground">
                    {t('descriptionLabel')}
                  </Label>
                  <Input
                    id="description"
                    placeholder={t('descriptionPlaceholder')}
                    value={description}
                    onChange={(e) => {
                      setDescription(e.target.value)
                      setFieldErrors((current) => clearFieldError(current, 'description'))
                    }}
                    className="h-8 text-sm"
                    aria-invalid={!!fieldErrors.description}
                  />
                  {fieldErrors.description && <p className="text-xs text-destructive">{fieldErrors.description}</p>}
                </div>
                <div className="flex items-center justify-between pt-1">
                  <Label htmlFor="enabled" className="text-xs text-muted-foreground">
                    {t('enabled')}
                  </Label>
                  <Switch id="enabled" checked={isEnabled} onCheckedChange={setIsEnabled} />
                </div>
              </CollapsibleContent>
            </Collapsible>

            <div className="space-y-3 py-2 border-t pt-4">
              <div className="text-sm font-medium">{t('codeEditor.runtime')}</div>
              <div className="space-y-1.5">
                <Label htmlFor="pythonPackages" className="text-xs text-muted-foreground">
                  {t('codeEditor.pythonPackages')}
                </Label>
                <Textarea
                  id="pythonPackages"
                  placeholder={t('codeEditor.pythonPackagesPlaceholder')}
                  value={pythonPackagesText}
                  onChange={(e) => {
                    setPythonPackagesText(e.target.value)
                    setFieldErrors((current) => clearFieldError(current, 'code_config.python_packages'))
                  }}
                  className="min-h-20 text-xs"
                  aria-invalid={!!fieldErrors['code_config.python_packages']}
                />
                {fieldErrors['code_config.python_packages'] && <p className="text-xs text-destructive">{fieldErrors['code_config.python_packages']}</p>}
                <p className="text-xs text-muted-foreground">{t('codeEditor.pythonPackagesHint')}</p>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="jsPackages" className="text-xs text-muted-foreground">
                  {t('codeEditor.jsPackages')}
                </Label>
                <Textarea
                  id="jsPackages"
                  placeholder={t('codeEditor.jsPackagesPlaceholder')}
                  value={jsPackagesText}
                  onChange={(e) => {
                    setJsPackagesText(e.target.value)
                    setFieldErrors((current) => clearFieldError(current, 'code_config.js_packages'))
                  }}
                  className="min-h-20 text-xs"
                  aria-invalid={!!fieldErrors['code_config.js_packages']}
                />
                {fieldErrors['code_config.js_packages'] && <p className="text-xs text-destructive">{fieldErrors['code_config.js_packages']}</p>}
                <p className="text-xs text-muted-foreground">{t('codeEditor.jsPackagesHint')}</p>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="pythonPackageIndexUrl" className="text-xs text-muted-foreground">
                  {t('codeEditor.pythonPackageIndexUrl')}
                </Label>
                <Input
                  id="pythonPackageIndexUrl"
                  placeholder={t('codeEditor.pythonPackageIndexUrlPlaceholder')}
                  value={pythonPackageIndexUrl}
                  onChange={(e) => {
                    setPythonPackageIndexUrl(e.target.value)
                    setFieldErrors((current) => clearFieldError(current, 'code_config.python_package_index_url'))
                  }}
                  className="h-8 text-xs"
                  aria-invalid={!!fieldErrors['code_config.python_package_index_url']}
                />
                {fieldErrors['code_config.python_package_index_url'] && <p className="text-xs text-destructive">{fieldErrors['code_config.python_package_index_url']}</p>}
                <p className="text-xs text-muted-foreground">{t('codeEditor.packageSourceUrlHint')}</p>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="nodePackageRegistryUrl" className="text-xs text-muted-foreground">
                  {t('codeEditor.nodePackageRegistryUrl')}
                </Label>
                <Input
                  id="nodePackageRegistryUrl"
                  placeholder={t('codeEditor.nodePackageRegistryUrlPlaceholder')}
                  value={nodePackageRegistryUrl}
                  onChange={(e) => {
                    setNodePackageRegistryUrl(e.target.value)
                    setFieldErrors((current) => clearFieldError(current, 'code_config.node_package_registry_url'))
                  }}
                  className="h-8 text-xs"
                  aria-invalid={!!fieldErrors['code_config.node_package_registry_url']}
                />
                {fieldErrors['code_config.node_package_registry_url'] && <p className="text-xs text-destructive">{fieldErrors['code_config.node_package_registry_url']}</p>}
                <p className="text-xs text-muted-foreground">{t('codeEditor.packageSourceUrlHint')}</p>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="command" className="text-xs text-muted-foreground">
                  {t('codeEditor.command')}
                </Label>
                <Textarea
                  id="command"
                  placeholder={t('codeEditor.commandPlaceholder')}
                  value={commandText}
                  onChange={(e) => {
                    setCommandText(e.target.value)
                    setFieldErrors((current) => clearFieldError(current, 'code_config.command'))
                  }}
                  className="min-h-20 text-xs font-mono"
                  aria-invalid={!!fieldErrors['code_config.command']}
                />
                {fieldErrors['code_config.command'] && <p className="text-xs text-destructive">{fieldErrors['code_config.command']}</p>}
                <p className="text-xs text-muted-foreground">{t('codeEditor.commandHint')}</p>
              </div>
              <div className="space-y-3 rounded-md border bg-background p-3">
                <div className="text-xs font-medium text-muted-foreground">{t('codeEditor.limits')}</div>
                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-1.5">
                    <Label htmlFor="timeoutSeconds" className="text-xs text-muted-foreground">{t('codeEditor.timeoutSeconds')}</Label>
                    <Input
                      id="timeoutSeconds"
                      value={timeoutSeconds}
                      onChange={(e) => {
                        setTimeoutSeconds(e.target.value)
                        setFieldErrors((current) => clearFieldError(current, 'code_config.limits.timeout_seconds'))
                      }}
                      className="h-8 text-xs"
                      aria-invalid={!!fieldErrors['code_config.limits.timeout_seconds']}
                    />
                    {fieldErrors['code_config.limits.timeout_seconds'] && <p className="text-xs text-destructive">{fieldErrors['code_config.limits.timeout_seconds']}</p>}
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="diskMb" className="text-xs text-muted-foreground">{t('codeEditor.diskMb')}</Label>
                    <Input
                      id="diskMb"
                      value={diskMb}
                      onChange={(e) => {
                        setDiskMb(e.target.value)
                        setFieldErrors((current) => clearFieldError(current, 'code_config.limits.disk_mb'))
                      }}
                      className="h-8 text-xs"
                      aria-invalid={!!fieldErrors['code_config.limits.disk_mb']}
                    />
                    {fieldErrors['code_config.limits.disk_mb'] && <p className="text-xs text-destructive">{fieldErrors['code_config.limits.disk_mb']}</p>}
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="maxStdoutKb" className="text-xs text-muted-foreground">{t('codeEditor.maxStdoutKb')}</Label>
                    <Input
                      id="maxStdoutKb"
                      value={maxStdoutKb}
                      onChange={(e) => {
                        setMaxStdoutKb(e.target.value)
                        setFieldErrors((current) => clearFieldError(current, 'code_config.limits.max_stdout_kb'))
                      }}
                      className="h-8 text-xs"
                      aria-invalid={!!fieldErrors['code_config.limits.max_stdout_kb']}
                    />
                    {fieldErrors['code_config.limits.max_stdout_kb'] && <p className="text-xs text-destructive">{fieldErrors['code_config.limits.max_stdout_kb']}</p>}
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="maxStderrKb" className="text-xs text-muted-foreground">{t('codeEditor.maxStderrKb')}</Label>
                    <Input
                      id="maxStderrKb"
                      value={maxStderrKb}
                      onChange={(e) => {
                        setMaxStderrKb(e.target.value)
                        setFieldErrors((current) => clearFieldError(current, 'code_config.limits.max_stderr_kb'))
                      }}
                      className="h-8 text-xs"
                      aria-invalid={!!fieldErrors['code_config.limits.max_stderr_kb']}
                    />
                    {fieldErrors['code_config.limits.max_stderr_kb'] && <p className="text-xs text-destructive">{fieldErrors['code_config.limits.max_stderr_kb']}</p>}
                  </div>
                </div>
              </div>
              <div className="space-y-3 rounded-md border bg-background p-3">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-medium text-muted-foreground">{t('codeEditor.artifacts')}</div>
                  <Button variant="outline" size="sm" className="h-7 text-xs" onClick={addArtifact}>
                    <Plus className="mr-1 h-3 w-3" />
                    {t('codeEditor.addArtifact')}
                  </Button>
                </div>
                {artifacts.map((artifact, index) => (
                  <div key={index} className="space-y-2 rounded-md border p-2">
                    <div className="flex items-center gap-2">
                      <Input
                        placeholder={t('codeEditor.artifactPathPlaceholder')}
                        value={artifact.path || ''}
                        onChange={(e) => {
                          updateArtifact(index, 'path', e.target.value)
                          setFieldErrors((current) => clearFieldError(current, `code_config.artifacts.${index}.path`))
                        }}
                        className="h-7 text-xs flex-1"
                        aria-invalid={!!fieldErrors[`code_config.artifacts.${index}.path`]}
                      />
                      <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" onClick={() => removeArtifact(index)}>
                        <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                      </Button>
                    </div>
                    <Input
                      placeholder={t('codeEditor.artifactDescription')}
                      value={artifact.description || ''}
                      onChange={(e) => {
                        updateArtifact(index, 'description', e.target.value)
                        setFieldErrors((current) => clearFieldError(current, `code_config.artifacts.${index}.description`))
                      }}
                      className="h-7 text-xs"
                      aria-invalid={!!fieldErrors[`code_config.artifacts.${index}.description`]}
                    />
                    {fieldErrors[`code_config.artifacts.${index}.path`] && <p className="text-xs text-destructive">{fieldErrors[`code_config.artifacts.${index}.path`]}</p>}
                    {fieldErrors[`code_config.artifacts.${index}.description`] && <p className="text-xs text-destructive">{fieldErrors[`code_config.artifacts.${index}.description`]}</p>}
                    <div className="flex items-center gap-2">
                      <Checkbox
                        id={`artifact-optional-${index}`}
                        checked={artifact.optional}
                        onCheckedChange={(checked) => updateArtifact(index, 'optional', checked === true)}
                      />
                      <Label htmlFor={`artifact-optional-${index}`} className="text-xs text-muted-foreground">{t('codeEditor.artifactOptional')}</Label>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* 参数定义 */}
            <Collapsible open={paramsOpen} onOpenChange={setParamsOpen}>
              <CollapsibleTrigger className="flex items-center gap-2 w-full py-2 text-sm font-medium hover:text-foreground/80 border-t pt-4">
                {paramsOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                {t('codeEditor.parameters')}
                <Badge variant="secondary" className="ml-auto text-xs">
                  {parameters.length}
                </Badge>
              </CollapsibleTrigger>
              <CollapsibleContent className="space-y-3 pt-2 pb-4">
                <p className="text-xs text-muted-foreground">{t('codeEditor.parametersHint')}</p>

                {parameters.map((param, index) => (
                  <div key={index} className="p-2 rounded-md border bg-background space-y-2">
                    <div className="flex items-center gap-2">
                      <Input
                        placeholder={t('codeEditor.paramName')}
                        value={param.name}
                        onChange={(e) => updateParameter(index, 'name', e.target.value)}
                        className="h-7 text-xs flex-1"
                      />
                      <Select
                        value={param.type}
                        onValueChange={(v) => updateParameter(index, 'type', v)}
                      >
                        <SelectTrigger size="xs" className="w-24">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent side="bottom" alignItemWithTrigger={false}>
                          {PARAM_TYPES.map((type) => (
                            <SelectItem key={type.value} value={type.value} className="text-xs">
                              {type.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 shrink-0"
                        onClick={() => removeParameter(index)}
                      >
                        <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                      </Button>
                    </div>
                    <Input
                      placeholder={t('codeEditor.paramDescription')}
                      value={param.description || ''}
                      onChange={(e) => updateParameter(index, 'description', e.target.value)}
                      className="h-7 text-xs"
                    />
                    <div className="flex items-center gap-2">
                      <Checkbox
                        id={`required-${index}`}
                        checked={param.required}
                        onCheckedChange={(checked) => updateParameter(index, 'required', checked)}
                      />
                      <Label htmlFor={`required-${index}`} className="text-xs text-muted-foreground">
                        {t('codeEditor.required')}
                      </Label>
                    </div>
                  </div>
                ))}

                <div className="flex gap-2">
                  <Button variant="outline" size="sm" className="flex-1 h-7 text-xs" onClick={addParameter}>
                    <Plus className="h-3 w-3 mr-1" />
                    {t('codeEditor.addParameter')}
                  </Button>
                  <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={generateTestInput}>
                    {t('codeEditor.generateTest')}
                  </Button>
                </div>
              </CollapsibleContent>
            </Collapsible>

            {/* 测试输入 */}
            <Collapsible open={testOpen} onOpenChange={setTestOpen}>
              <CollapsibleTrigger className="flex items-center gap-2 w-full py-2 text-sm font-medium hover:text-foreground/80 border-t pt-4">
                {testOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                {t('codeEditor.testInput')}
              </CollapsibleTrigger>
              <CollapsibleContent className="space-y-2 pt-2 pb-4">
                <Label className="text-xs text-muted-foreground">{t('codeEditor.inputParams')}</Label>
                <Textarea
                  className="h-28 text-xs font-mono resize-none"
                  placeholder='{"input": "test value"}'
                  value={testInput}
                  onChange={(e) => {
                    setTestInput(e.target.value)
                    setFieldErrors((current) => clearFieldError(current, 'params'))
                  }}
                  aria-invalid={!!fieldErrors.params}
                />
                {fieldErrors.params && <p className="text-xs text-destructive">{fieldErrors.params}</p>}
                <p className="text-xs text-muted-foreground">{t('codeEditor.inputHint')}</p>
              </CollapsibleContent>
            </Collapsible>

            {/* 输出结果 */}
            <Collapsible open={outputOpen} onOpenChange={setOutputOpen}>
              <div className="flex items-center gap-2 border-t pt-4">
                <CollapsibleTrigger className="flex items-center gap-2 flex-1 py-2 text-sm font-medium hover:text-foreground/80">
                  {outputOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                  {t('codeEditor.outputResult')}
                </CollapsibleTrigger>
                {testOutput && (
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-5 w-5 shrink-0"
                    onClick={() => setTestOutput('')}
                  >
                    <X className="h-3 w-3" />
                  </Button>
                )}
              </div>
              <CollapsibleContent className="pt-2 pb-4">
                <div
                  className={cn(
                    'rounded-md border bg-muted/50 p-3 min-h-20 max-h-64 overflow-auto',
                    !testOutput && 'flex items-center justify-center'
                  )}
                >
                  {testOutput ? (
                    <pre className="text-xs font-mono whitespace-pre-wrap break-all">{testOutput}</pre>
                  ) : (
                    <span className="text-xs text-muted-foreground">{t('codeEditor.noOutput')}</span>
                  )}
                </div>
              </CollapsibleContent>
            </Collapsible>
          </div>
        </aside>
      </div>
    </div>
  )
}

export default function CodeToolPage() {
  return (
    <RoutePermissionGuard>
      <Suspense fallback={
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    }>
      <CodeToolPageContent />
      </Suspense>
    </RoutePermissionGuard>
  )
}
