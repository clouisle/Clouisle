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
import { toast } from 'sonner'
import { toolsApi, ToolCreateInput, ToolUpdateInput, CodeConfig, ToolParameter, ToolCategory } from '@/lib/api/tools'
import { teamsApi, UserTeamInfo } from '@/lib/api'
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

function CodeToolPageContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const toolId = searchParams.get('id')
  const teamIdParam = searchParams.get('teamId')
  const t = useTranslations('tools')
  const tCommon = useTranslations('common')

  // 团队信息
  const [teams, setTeams] = useState<UserTeamInfo[]>([])
  const [currentTeamId, setCurrentTeamId] = useState<string>(teamIdParam || '')

  // 工具信息
  const [name, setName] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [description, setDescription] = useState('')
  const [icon, setIcon] = useState('📜')
  const [category, setCategory] = useState<ToolCategory>('code')
  const [isEnabled, setIsEnabled] = useState(true)

  // 参数定义
  const [parameters, setParameters] = useState<ToolParameter[]>([
    { name: 'input', type: 'string', description: '输入内容', required: true },
  ])

  // 代码配置
  const [language, setLanguage] = useState<CodeLanguage>('javascript')
  const [code, setCode] = useState(DEFAULT_CODE.javascript)
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
        const data = await teamsApi.getMyTeams()
        setTeams(data)
        if (data.length > 0 && !currentTeamId) {
          setCurrentTeamId(data[0].id)
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
      const tool = await toolsApi.getById(id)
      setName(tool.name)
      setDisplayName(tool.display_name)
      setDescription(tool.description)
      setIcon(tool.icon || '📜')
      setCategory(tool.category || 'code')
      setIsEnabled(tool.is_enabled)

      // 加载参数
      if (tool.parameters && tool.parameters.length > 0) {
        setParameters(tool.parameters)
      }

      if (tool.code_config) {
        const loadedCode = tool.code_config.code || DEFAULT_CODE[tool.code_config.language as CodeLanguage]
        setLanguage(tool.code_config.language as CodeLanguage)
        setCode(loadedCode)
        // 加载的代码如果不是默认代码，标记为已修改
        isCodeModified.current = loadedCode.trim() !== DEFAULT_CODE[tool.code_config.language as CodeLanguage].trim()
      }
    } catch {
      toast.error(t('error.loadFailed'))
      router.push('/tools')
    } finally {
      setIsLoading(false)
    }
  }, [t, router])

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

  const handleSave = async () => {
    if (!name.trim()) {
      toast.error(t('error.nameRequired'))
      return
    }

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
      const codeConfig: CodeConfig = {
        language,
        code,
        dependencies: [],
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
        await toolsApi.update(toolId, data)
        toast.success(t('successMessages.updated'))
      } else {
        await toolsApi.create(currentTeamId, data as ToolCreateInput)
        toast.success(t('successMessages.created'))
        router.push('/tools')
      }
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : t('error.saveFailed')
      toast.error(message)
    } finally {
      setIsSaving(false)
    }
  }

  const handleRun = async () => {
    setIsRunning(true)
    setTestOutput('')
    setOutputOpen(true)

    try {
      let params: Record<string, unknown>
      try {
        params = JSON.parse(testInput)
      } catch {
        setTestOutput('Error: Invalid JSON input')
        setIsRunning(false)
        return
      }

      const result = await toolsApi.executeCode({
        language,
        code,
        params,
        timeout: 30,
      })

      let output = ''
      if (result.logs) {
        output += `📝 Logs:\n${result.logs}\n\n`
      }
      if (result.success) {
        const resultStr =
          typeof result.result === 'string'
            ? result.result
            : JSON.stringify(result.result, null, 2)
        output += `✅ Result:\n${resultStr}`
      } else {
        output += `❌ Error:\n${result.error || 'Execution failed'}`
      }
      if (result.duration_ms !== undefined) {
        output += `\n\n⏱️ Duration: ${result.duration_ms}ms`
      }
      setTestOutput(output)
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Execution failed'
      setTestOutput(`❌ Error: ${message}`)
    } finally {
      setIsRunning(false)
    }
  }

  const handleBack = () => {
    router.push('/tools')
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
              <SelectTrigger className="w-32 h-8">
                <SelectValue />
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
            <SelectTrigger className="w-28 h-8">
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

          <Button variant="outline" size="sm" onClick={handleRun} disabled={isRunning || !code.trim()}>
            {isRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            <span className="ml-1.5">{t('codeEditor.run')}</span>
          </Button>

          <Button size="sm" onClick={handleSave} disabled={isSaving}>
            {isSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            <span className="ml-1.5">{tCommon('save')}</span>
          </Button>
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
                    onChange={(e) => setName(e.target.value)}
                    disabled={isEditing}
                    className="h-8 text-sm"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="displayName" className="text-xs text-muted-foreground">
                    {t('displayName')}
                  </Label>
                  <Input
                    id="displayName"
                    placeholder="My Tool"
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    className="h-8 text-sm"
                  />
                </div>
                <div className="flex gap-2">
                  <div className="space-y-1.5">
                    <Label htmlFor="icon" className="text-xs text-muted-foreground">
                      {t('icon')}
                    </Label>
                    <Input
                      id="icon"
                      className="w-12 h-8 text-center text-lg"
                      value={icon}
                      onChange={(e) => setIcon(e.target.value)}
                      maxLength={2}
                    />
                  </div>
                  <div className="flex-1 space-y-1.5">
                    <Label htmlFor="category" className="text-xs text-muted-foreground">
                      {t('category')}
                    </Label>
                    <Select value={category} onValueChange={(v) => setCategory(v as ToolCategory)}>
                      <SelectTrigger id="category" size="sm">
                        <SelectValue>{t(`categories.${category}`)}</SelectValue>
                      </SelectTrigger>
                      <SelectContent side="bottom" alignItemWithTrigger={false}>
                        <SelectItem value="time">{t('categories.time')}</SelectItem>
                        <SelectItem value="math">{t('categories.math')}</SelectItem>
                        <SelectItem value="search">{t('categories.search')}</SelectItem>
                        <SelectItem value="web">{t('categories.web')}</SelectItem>
                        <SelectItem value="file">{t('categories.file')}</SelectItem>
                        <SelectItem value="code">{t('categories.code')}</SelectItem>
                        <SelectItem value="api">{t('categories.api')}</SelectItem>
                        <SelectItem value="data">{t('categories.data')}</SelectItem>
                        <SelectItem value="other">{t('categories.other')}</SelectItem>
                      </SelectContent>
                    </Select>
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
                    onChange={(e) => setDescription(e.target.value)}
                    className="h-8 text-sm"
                  />
                </div>
                <div className="flex items-center justify-between pt-1">
                  <Label htmlFor="enabled" className="text-xs text-muted-foreground">
                    {t('enabled')}
                  </Label>
                  <Switch id="enabled" checked={isEnabled} onCheckedChange={setIsEnabled} />
                </div>
              </CollapsibleContent>
            </Collapsible>

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
                  onChange={(e) => setTestInput(e.target.value)}
                />
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
    <Suspense fallback={
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    }>
      <CodeToolPageContent />
    </Suspense>
  )
}
