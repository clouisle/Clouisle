import { describe, expect, test } from 'bun:test'
import {
  categorizeTool,
  cleanToolDisplayName,
  getActiveToolActions,
} from './tool-action-utils'
import type { MessagePart } from './types'

describe('tool-action-utils', () => {
  test('cleans raw function identifiers into human-readable capitalized names', () => {
    expect(cleanToolDisplayName('get_user_profile')).toBe('Get User Profile')
    expect(cleanToolDisplayName('fetchStockData')).toBe('Fetch Stock Data')
    expect(cleanToolDisplayName('my-custom-tool')).toBe('My Custom Tool')
    expect(cleanToolDisplayName('custom_api', '查询客户信息')).toBe('查询客户信息')
  })

  test('categorizes builtin tools into semantic actions', () => {
    expect(categorizeTool('read_file')).toBe('reading_file')
    expect(categorizeTool('cat_file')).toBe('reading_file')
    expect(categorizeTool('read_asset')).toBe('reading_file')
    expect(categorizeTool('search_asset')).toBe('reading_file')
    expect(categorizeTool('inspect_asset')).toBe('reading_file')
    expect(categorizeTool('view_asset')).toBe('reading_file')
    expect(categorizeTool('list_assets')).toBe('browsing_dir')
    expect(categorizeTool('materialize_asset')).toBe('editing_file')
    expect(categorizeTool('write_file')).toBe('editing_file')
    expect(categorizeTool('list_dir')).toBe('browsing_dir')
    expect(categorizeTool('browse_dir')).toBe('browsing_dir')
    expect(categorizeTool('python_runner')).toBe('running_code')
    expect(categorizeTool('bash_tool')).toBe('executing_command')
    expect(categorizeTool('calculator')).toBe('calculating')
    expect(categorizeTool('web_search')).toBe('searching_web')
    expect(categorizeTool('fetch_webpage')).toBe('searching_web')
    expect(categorizeTool('knowledge_base')).toBe('searching_kb')
    expect(categorizeTool('generate_image')).toBe('generating_media')
    expect(categorizeTool('artifact')).toBe('collecting_artifacts')
    expect(categorizeTool('artifacts')).toBe('collecting_artifacts')
    expect(categorizeTool('custom_tool', {}, '生成下载链接')).toBe('collecting_artifacts')
    // Ensure bounded matching does not falsely categorize unrelated words
    expect(categorizeTool('sales_report')).not.toBe('browsing_dir')
    expect(categorizeTool('false_alarm')).not.toBe('browsing_dir')
    expect(categorizeTool('tools_api')).not.toBe('browsing_dir')
  })
  test('categorizes user-defined custom tools using verb prefixes and arguments', () => {
    expect(categorizeTool('query_order_status')).toBe('querying_custom')
    expect(categorizeTool('fetch_metrics')).toBe('querying_custom')
    expect(categorizeTool('send_slack_message')).toBe('sending_custom')
    expect(categorizeTool('post_webhook')).toBe('sending_custom')
    expect(categorizeTool('create_jira_issue')).toBe('creating_custom')
    expect(categorizeTool('api_weather_v2', { url: 'https://api.weather.com' })).toBe('requesting_custom')
    expect(categorizeTool('unknown_custom_service')).toBe('calling_custom')
  })

  test('resolves single, parallel, and idle active tool actions from message parts', () => {
    const idleParts: MessagePart[] = [
      { type: 'tool-call', toolCallId: 't1', toolName: 'read_file', input: {}, state: 'done' },
      { type: 'tool-result', toolCallId: 't1', toolName: 'read_file', output: 'ok' },
    ]
    expect(getActiveToolActions(idleParts)).toEqual([])

    const singlePart: MessagePart[] = [
      { type: 'tool-call', toolCallId: 't1', toolName: 'read_file', input: {}, state: 'running' },
    ]
    expect(getActiveToolActions(singlePart)).toEqual([
      { category: 'reading_file', toolName: 'read_file', displayName: 'Read File' },
    ])

    const parallelParts: MessagePart[] = [
      { type: 'tool-call', toolCallId: 't1', toolName: 'query_order', input: {}, state: 'running' },
      { type: 'tool-call', toolCallId: 't2', toolName: 'send_notice', input: {}, state: 'running' },
    ]
    expect(getActiveToolActions(parallelParts)).toHaveLength(2)
    expect(getActiveToolActions(parallelParts)[0].category).toBe('querying_custom')
    expect(getActiveToolActions(parallelParts)[1].category).toBe('sending_custom')
  })
})
