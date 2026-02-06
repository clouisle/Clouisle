'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Copy, Check, ChevronDown, ChevronRight } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { type VariableDefinition } from '@/lib/api/workflows'

interface CodeExamplesProps {
  webhookUrl: string
  variables: VariableDefinition[]
}

export function CodeExamples({ webhookUrl, variables }: CodeExamplesProps) {
  const t = useTranslations('workflow')
  const [copiedIndex, setCopiedIndex] = React.useState<number | null>(null)
  const [expandedIndex, setExpandedIndex] = React.useState<number>(0)

  const handleCopy = async (code: string, index: number) => {
    await navigator.clipboard.writeText(code)
    setCopiedIndex(index)
    setTimeout(() => setCopiedIndex(null), 2000)
  }

  // Generate example input based on variables
  const generateExampleInput = () => {
    if (!variables || variables.length === 0) {
      return '{}'
    }

    const example: Record<string, unknown> = {}
    variables.forEach((variable) => {
      switch (variable.type) {
        case 'text':
          example[variable.name] = 'example text'
          break
        case 'number':
          example[variable.name] = 42
          break
        case 'boolean':
          example[variable.name] = true
          break
        case 'array':
          example[variable.name] = ['item1', 'item2']
          break
        case 'object':
          example[variable.name] = { key: 'value' }
          break
        default:
          example[variable.name] = 'value'
      }
    })

    return JSON.stringify(example, null, 2)
  }

  const exampleInput = generateExampleInput()

  const examples = [
    {
      title: 'cURL',
      language: 'bash',
      code: `curl -X POST \\
  ${webhookUrl} \\
  -H "Content-Type: application/json" \\
  -d '${exampleInput.replace(/\n/g, '\n  ')}'`,
    },
    {
      title: 'Python',
      language: 'python',
      code: `import requests

url = "${webhookUrl}"
data = ${exampleInput}

response = requests.post(url, json=data)
result = response.json()

print(f"Run ID: {result['data']['run_id']}")
print(f"Status: {result['data']['status']}")
print(f"Stream URL: {result['data']['stream_url']}")`,
    },
    {
      title: 'JavaScript (fetch)',
      language: 'javascript',
      code: `const response = await fetch('${webhookUrl}', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify(${exampleInput}),
});

const result = await response.json();
console.log('Run ID:', result.data.run_id);
console.log('Status:', result.data.status);
console.log('Stream URL:', result.data.stream_url);`,
    },
    {
      title: 'Node.js (axios)',
      language: 'javascript',
      code: `const axios = require('axios');

const url = '${webhookUrl}';
const data = ${exampleInput};

axios.post(url, data)
  .then(response => {
    const result = response.data;
    console.log('Run ID:', result.data.run_id);
    console.log('Status:', result.data.status);
    console.log('Stream URL:', result.data.stream_url);
  })
  .catch(error => {
    console.error('Error:', error.response?.data || error.message);
  });`,
    },
  ]

  return (
    <div className="space-y-4">
      {examples.map((example, index) => (
        <Card key={index}>
          <CardHeader
            className="cursor-pointer"
            onClick={() => setExpandedIndex(expandedIndex === index ? -1 : index)}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                {expandedIndex === index ? (
                  <ChevronDown className="h-4 w-4" />
                ) : (
                  <ChevronRight className="h-4 w-4" />
                )}
                <CardTitle className="text-base">{example.title}</CardTitle>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={(e) => {
                  e.stopPropagation()
                  handleCopy(example.code, index)
                }}
              >
                {copiedIndex === index ? (
                  <>
                    <Check className="mr-2 h-4 w-4 text-green-600" />
                    {t('copied')}
                  </>
                ) : (
                  <>
                    <Copy className="mr-2 h-4 w-4" />
                    {t('copy')}
                  </>
                )}
              </Button>
            </div>
          </CardHeader>
          {expandedIndex === index && (
            <CardContent>
              <pre className="overflow-x-auto rounded-lg bg-muted p-4">
                <code className="text-sm font-mono">{example.code}</code>
              </pre>
            </CardContent>
          )}
        </Card>
      ))}
    </div>
  )
}
