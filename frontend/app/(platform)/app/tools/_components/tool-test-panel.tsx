'use client'

import { useState, useEffect } from 'react'
import Image from 'next/image'
import { useTranslations } from 'next-intl'
import { Tool, ToolParameter, toolsApi, ToolExecuteResponse, McpToolInfo } from '@/lib/api'
import { useTeam } from '@/contexts/team-context'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { 
  Sheet,
  SheetContent, 
  SheetDescription, 
  SheetHeader, 
  SheetTitle 
} from '@/components/ui/sheet'
import { 
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Play, Loader2, CheckCircle, XCircle, Clock, Copy, Check, RefreshCw } from 'lucide-react'
import { toast } from 'sonner'

interface ToolTestPanelProps {
  tool: Tool | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function ToolTestPanel({ tool, open, onOpenChange }: ToolTestPanelProps) {
  const t = useTranslations('platform.tools')
  const [args, setArgs] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ToolExecuteResponse | null>(null)
  const [copied, setCopied] = useState(false)
  const { currentTeam } = useTeam()

  // MCP 相关状态
  const [mcpTools, setMcpTools] = useState<McpToolInfo[]>([])
  const [selectedMcpTool, setSelectedMcpTool] = useState<string>('')
  const [loadingMcpTools, setLoadingMcpTools] = useState(false)

  // 加载 MCP 工具列表
  const loadMcpTools = async () => {
    if (!tool || tool.type !== 'mcp' || !tool.mcp_config) return

    setLoadingMcpTools(true)
    try {
      const response = await toolsApi.listMcpTools(tool.mcp_config)
      setMcpTools(response.tools)
      if (response.tools.length > 0) {
        setSelectedMcpTool(response.tools[0].name)
      }
    } catch (error) {
      console.error('Failed to load MCP tools:', error)
    } finally {
      setLoadingMcpTools(false)
    }
  }

  // 当打开面板且是 MCP 工具时，加载工具列表
  useEffect(() => {
    if (open && tool?.type === 'mcp') {
      loadMcpTools()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, tool])

  // 获取当前选中的 MCP 工具参数
  const currentMcpToolParams = mcpTools.find(t => t.name === selectedMcpTool)?.parameters

  // 重置状态
  const handleOpenChange = (isOpen: boolean) => {
    if (!isOpen) {
      setArgs({})
      setResult(null)
      setMcpTools([])
      setSelectedMcpTool('')
    }
    onOpenChange(isOpen)
  }

  // 执行测试
  const handleTest = async () => {
    if (!tool) return

    setLoading(true)
    setResult(null)

    try {
      // 转换参数类型
      const typedArgs: Record<string, unknown> = {}
      
      // 对于 MCP 工具，使用选中的工具的参数
      if (tool.type === 'mcp') {
        // MCP 工具参数处理 - 直接使用用户输入的值
        Object.entries(args).forEach(([key, value]) => {
          if (value !== undefined && value !== '') {
            // 尝试解析为 JSON，如果失败则保持字符串
            try {
              typedArgs[key] = JSON.parse(value)
            } catch {
              typedArgs[key] = value
            }
          }
        })
        // 添加 MCP 工具名称
        typedArgs['__tool_name__'] = selectedMcpTool
      } else {
        // 普通工具参数处理
        tool.parameters.forEach((param) => {
          const value = args[param.name]
          if (value !== undefined && value !== '') {
            if (param.type === 'integer') {
              typedArgs[param.name] = parseInt(value, 10)
            } else if (param.type === 'number') {
              typedArgs[param.name] = parseFloat(value)
            } else if (param.type === 'boolean') {
              typedArgs[param.name] = value === 'true'
            } else if (param.type === 'array' || param.type === 'object') {
              // 尝试解析 JSON
              try {
                typedArgs[param.name] = JSON.parse(value)
              } catch {
                // 如果解析失败，保持原始字符串
                typedArgs[param.name] = value
              }
            } else {
              typedArgs[param.name] = value
            }
          }
        })
      }

      const response = await toolsApi.test({
        name: tool.name,
        arguments: typedArgs,
      }, currentTeam?.id)
      setResult(response)
    } catch (error) {
      console.error('Tool test error:', error)
    } finally {
      setLoading(false)
    }
  }

  // 复制结果
  const handleCopy = async () => {
    if (!result) return
    try {
      await navigator.clipboard.writeText(JSON.stringify(result.result, null, 2))
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
      toast.success(t('copied'))
    } catch {
      toast.error(t('copyFailed'))
    }
  }

  if (!tool) return null

  // 判断图标是否为 URL
  const isIconUrl = tool.icon?.startsWith('http')

  return (
    <Sheet open={open} onOpenChange={handleOpenChange}>
      <SheetContent className="w-[500px] sm:max-w-[500px] overflow-y-auto">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            {isIconUrl ? (
              <div className="relative h-6 w-6 rounded overflow-hidden shrink-0">
                <Image
                  src={tool.icon || ''}
                  alt={tool.display_name}
                  fill
                  className="object-cover"
                  unoptimized
                />
              </div>
            ) : (
              <span className="text-xl">{tool.icon}</span>
            )}
            {tool.display_name}
          </SheetTitle>
          <SheetDescription>{tool.description}</SheetDescription>
        </SheetHeader>

        <div className="space-y-6 px-4 pb-4">
          {/* MCP 工具选择 */}
          {tool.type === 'mcp' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-medium">{t('mcpDialog.availableTools')}</h4>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={loadMcpTools}
                  disabled={loadingMcpTools}
                >
                  {loadingMcpTools ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <RefreshCw className="h-4 w-4" />
                  )}
                </Button>
              </div>
              
              {loadingMcpTools ? (
                <div className="flex items-center justify-center py-4">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : mcpTools.length > 0 ? (
                <Select value={selectedMcpTool} onValueChange={(v) => {
                  setSelectedMcpTool(v ?? '')
                  setArgs({}) // 切换工具时清空参数
                }}>
                  <SelectTrigger>
                    <SelectValue>{selectedMcpTool || t('selectTool')}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {mcpTools.map((mcpTool) => (
                      <SelectItem key={mcpTool.name} value={mcpTool.name}>
                        <div className="flex flex-col items-start">
                          <span>{mcpTool.name}</span>
                          {mcpTool.description && (
                            <span className="text-xs text-muted-foreground truncate max-w-[250px]">
                              {mcpTool.description}
                            </span>
                          )}
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-2">
                  {t('mcpDialog.noToolsAvailable')}
                </p>
              )}

              {/* 显示选中 MCP 工具的参数 */}
              {selectedMcpTool && currentMcpToolParams && (
                <McpParameterInputs
                  parameters={currentMcpToolParams}
                  args={args}
                  onChange={setArgs}
                />
              )}
            </div>
          )}

          {/* 普通工具参数输入 */}
          {tool.type !== 'mcp' && tool.parameters.length > 0 && (
            <div className="space-y-4">
              <h4 className="text-sm font-medium">{t('parameters')}</h4>
              {tool.parameters.map((param) => (
                <ParameterInput
                  key={param.name}
                  parameter={param}
                  value={args[param.name] || ''}
                  onChange={(value) => setArgs({ ...args, [param.name]: value })}
                />
              ))}
            </div>
          )}

          {/* 执行按钮 */}
          <Button 
            onClick={handleTest} 
            disabled={loading || (tool.type === 'mcp' && !selectedMcpTool)} 
            className="w-full"
          >
            {loading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                {t('testing')}
              </>
            ) : (
              <>
                <Play className="mr-2 h-4 w-4" />
                {t('runTest')}
              </>
            )}
          </Button>

          {/* 执行结果 */}
          {result && (
            <>
              <Separator />
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-sm font-medium">{t('result')}</h4>
                  <div className="flex items-center gap-2">
                    {result.duration_ms && (
                      <Badge variant="outline" className="text-xs">
                        <Clock className="mr-1 h-3 w-3" />
                        {result.duration_ms}ms
                      </Badge>
                    )}
                    {result.success ? (
                      <Badge className="bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300">
                        <CheckCircle className="mr-1 h-3 w-3" />
                        {t('success')}
                      </Badge>
                    ) : (
                      <Badge className="bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300">
                        <XCircle className="mr-1 h-3 w-3" />
                        {t('failed')}
                      </Badge>
                    )}
                  </div>
                </div>

                <Card>
                  <CardContent className="p-3 relative">
                    {result.success ? (
                      <>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="absolute top-2 right-2 h-7 w-7 p-0"
                          onClick={handleCopy}
                        >
                          {copied ? (
                            <Check className="h-3.5 w-3.5 text-green-500" />
                          ) : (
                            <Copy className="h-3.5 w-3.5" />
                          )}
                        </Button>
                        <pre className="text-xs overflow-auto max-h-[300px] pr-8">
                          {JSON.stringify(result.result, null, 2)}
                        </pre>
                      </>
                    ) : (
                      <p className="text-sm text-destructive">{result.error}</p>
                    )}
                  </CardContent>
                </Card>
              </div>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}

// MCP 参数输入组件
function McpParameterInputs({
  parameters,
  args,
  onChange,
}: {
  parameters: Record<string, unknown>
  args: Record<string, string>
  onChange: (args: Record<string, string>) => void
}) {
  const t = useTranslations('platform.tools')
  
  // 解析 JSON Schema 参数
  const properties = (parameters as { properties?: Record<string, { type?: string; description?: string; enum?: string[] }> }).properties || {}
  const required = (parameters as { required?: string[] }).required || []

  if (Object.keys(properties).length === 0) {
    return (
      <p className="text-xs text-muted-foreground">{t('noParameters')}</p>
    )
  }

  // 渲染输入控件
  const renderInput = (name: string, schema: { type?: string; description?: string; enum?: string[] }) => {
    const value = args[name] || ''
    const handleChange = (newValue: string) => onChange({ ...args, [name]: newValue })

    // 枚举类型
    if (schema.enum) {
      return (
        <select
          id={name}
          value={value}
          onChange={(e) => handleChange(e.target.value)}
          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs transition-colors focus:ring-2 focus:ring-ring"
        >
          <option value="">{t('selectOption')}</option>
          {schema.enum.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      )
    }

    // 布尔类型
    if (schema.type === 'boolean') {
      return (
        <select
          id={name}
          value={value}
          onChange={(e) => handleChange(e.target.value)}
          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs transition-colors focus:ring-2 focus:ring-ring"
        >
          <option value="">{t('selectOption')}</option>
          <option value="true">true</option>
          <option value="false">false</option>
        </select>
      )
    }

    // 数组类型
    if (schema.type === 'array') {
      return (
        <textarea
          id={name}
          value={value}
          onChange={(e) => handleChange(e.target.value)}
          placeholder='["item1", "item2"]'
          className="flex min-h-[80px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs transition-colors focus:ring-2 focus:ring-ring font-mono"
          rows={3}
        />
      )
    }

    // 对象类型
    if (schema.type === 'object') {
      return (
        <textarea
          id={name}
          value={value}
          onChange={(e) => handleChange(e.target.value)}
          placeholder='{"key": "value"}'
          className="flex min-h-[80px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs transition-colors focus:ring-2 focus:ring-ring font-mono"
          rows={3}
        />
      )
    }

    // 数字类型
    if (schema.type === 'integer' || schema.type === 'number') {
      return (
        <Input
          id={name}
          type="number"
          value={value}
          onChange={(e) => handleChange(e.target.value)}
          step={schema.type === 'integer' ? '1' : 'any'}
        />
      )
    }

    // 默认字符串类型
    return (
      <Input
        id={name}
        value={value}
        onChange={(e) => handleChange(e.target.value)}
      />
    )
  }

  return (
    <div className="space-y-3">
      <h4 className="text-sm font-medium">{t('parameters')}</h4>
      {Object.entries(properties).map(([name, schema]) => (
        <div key={name} className="space-y-1">
          <div className="flex items-center gap-2">
            <Label htmlFor={name} className="text-sm">{name}</Label>
            {required.includes(name) && (
              <Badge variant="outline" className="text-xs px-1 py-0">{t('required')}</Badge>
            )}
            {schema.type && (
              <Badge variant="secondary" className="text-xs px-1 py-0">{schema.type}</Badge>
            )}
          </div>
          {schema.description && (
            <p className="text-xs text-muted-foreground">{schema.description}</p>
          )}
          {renderInput(name, schema)}
        </div>
      ))}
    </div>
  )
}

// 参数输入组件
function ParameterInput({
  parameter,
  value,
  onChange,
}: {
  parameter: ToolParameter
  value: string
  onChange: (value: string) => void
}) {
  const t = useTranslations('platform.tools')

  // 渲染输入控件
  const renderInput = () => {
    // 枚举类型 - 下拉选择
    if (parameter.enum) {
      return (
        <select
          id={parameter.name}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs transition-colors focus:ring-2 focus:ring-ring"
        >
          <option value="">{t('selectOption')}</option>
          {parameter.enum.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      )
    }

    // 布尔类型 - 下拉选择
    if (parameter.type === 'boolean') {
      return (
        <select
          id={parameter.name}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs transition-colors focus:ring-2 focus:ring-ring"
        >
          <option value="">{t('selectOption')}</option>
          <option value="true">true</option>
          <option value="false">false</option>
        </select>
      )
    }

    // 数组类型 - 多行文本框
    if (parameter.type === 'array') {
      return (
        <textarea
          id={parameter.name}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder='["item1", "item2"]'
          className="flex min-h-[80px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs transition-colors focus:ring-2 focus:ring-ring font-mono"
          rows={3}
        />
      )
    }

    // 对象类型 - 多行文本框
    if (parameter.type === 'object') {
      return (
        <textarea
          id={parameter.name}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder='{"key": "value"}'
          className="flex min-h-[80px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs transition-colors focus:ring-2 focus:ring-ring font-mono"
          rows={3}
        />
      )
    }

    // 数字类型
    if (parameter.type === 'integer' || parameter.type === 'number') {
      return (
        <Input
          id={parameter.name}
          type="number"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={parameter.default?.toString() || ''}
          step={parameter.type === 'integer' ? '1' : 'any'}
        />
      )
    }

    // 默认字符串类型
    return (
      <Input
        id={parameter.name}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={parameter.default?.toString() || ''}
      />
    )
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Label htmlFor={parameter.name} className="text-sm">
          {parameter.name}
        </Label>
        {parameter.required && (
          <Badge variant="outline" className="text-xs px-1 py-0">
            {t('required')}
          </Badge>
        )}
        <Badge variant="secondary" className="text-xs px-1 py-0">
          {parameter.type}
        </Badge>
      </div>
      {parameter.description && (
        <p className="text-xs text-muted-foreground">{parameter.description}</p>
      )}
      {renderInput()}
    </div>
  )
}

export default ToolTestPanel
