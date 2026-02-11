# Agent Configuration

This guide covers how to configure AI agents in Clouisle.

## Overview

Agent configuration includes:

- **Basic settings**: Name, description, model
- **System prompt**: Define agent behavior
- **LLM parameters**: Temperature, max tokens, etc.
- **Knowledge bases**: Attach knowledge sources
- **Tools**: Enable agent capabilities
- **RAG settings**: Configure retrieval
- **Permissions**: Control access

## Accessing Agent Configuration

### From Agent List

1. Navigate to **Agents**
2. Click on agent to configure
3. Click **Settings** or **Edit** button
4. Modify configuration
5. Click **Save Changes**

### Configuration Sections

- **Basic Information**: Name, description, icon
- **Model Settings**: LLM model and parameters
- **System Prompt**: Agent instructions
- **Knowledge Bases**: Attached knowledge sources
- **Tools**: Enabled capabilities
- **RAG Configuration**: Retrieval settings
- **Advanced Settings**: Additional options

## Basic Information

### Agent Details

**Configure basic information:**

```yaml
Name: Customer Support Agent
Description: Handles customer inquiries and support tickets
Icon: 🤖
Team: Support Team
Status: Active
Visibility: Private
```

**Fields:**
- **Name**: Display name (max 100 chars)
- **Description**: Agent purpose (max 500 chars)
- **Icon**: Emoji or image URL
- **Team**: Team ownership
- **Status**: Active or Inactive
- **Visibility**: Private (team only) or Public

**Best Practices:**
- Use descriptive names
- Clearly state agent purpose
- Choose appropriate icon
- Keep description concise

## Model Selection

### Choose LLM Model

**Available Models:**
- GPT-4 Turbo (OpenAI)
- GPT-4 (OpenAI)
- GPT-3.5 Turbo (OpenAI)
- Claude 3.5 Sonnet (Anthropic)
- Claude 3 Opus (Anthropic)
- Claude 3 Haiku (Anthropic)
- Custom models

**Model Selection:**

```yaml
Model: GPT-4 Turbo
Provider: OpenAI
Context Length: 128,000 tokens
Capabilities:
  - Function calling
  - Streaming
  - JSON mode
Cost: $0.01/1K input, $0.03/1K output
```

**Considerations:**
- **Performance**: More capable models = better responses
- **Cost**: Balance quality vs. cost
- **Speed**: Faster models for real-time chat
- **Context**: Longer context for complex tasks
- **Capabilities**: Function calling, vision, etc.

### Model Comparison

| Model | Context | Speed | Cost | Best For |
|-------|---------|-------|------|----------|
| GPT-4 Turbo | 128K | Medium | $$$ | Complex tasks |
| GPT-3.5 Turbo | 16K | Fast | $ | Simple queries |
| Claude 3.5 Sonnet | 200K | Medium | $$ | Long documents |
| Claude 3 Haiku | 200K | Very Fast | $ | Quick responses |

## System Prompt

### Define Agent Behavior

**System Prompt Structure:**

```
You are a [role] that [purpose].

Your responsibilities:
- [Responsibility 1]
- [Responsibility 2]
- [Responsibility 3]

Guidelines:
- [Guideline 1]
- [Guideline 2]
- [Guideline 3]

Tone: [Professional/Friendly/Casual]
```

**Example - Customer Support Agent:**

```
You are a helpful customer support agent for Clouisle, an AI platform.

Your responsibilities:
- Answer customer questions about features and usage
- Help troubleshoot technical issues
- Guide users through common tasks
- Escalate complex issues to human support

Guidelines:
- Always be polite and professional
- Use the knowledge base to provide accurate information
- If you don't know something, admit it and offer to escalate
- Keep responses concise but complete
- Use examples when helpful

Tone: Friendly and professional
```

**Example - Sales Assistant:**

```
You are a sales assistant helping potential customers understand Clouisle.

Your responsibilities:
- Explain product features and benefits
- Answer pricing questions
- Qualify leads and understand needs
- Schedule demos with sales team

Guidelines:
- Focus on customer needs, not just features
- Be enthusiastic but not pushy
- Use specific examples and use cases
- Highlight relevant features based on customer needs
- Always include a clear call-to-action

Tone: Professional and consultative
```

### System Prompt Best Practices

**✅ Do:**
- Be specific about role and purpose
- Include clear guidelines
- Define tone and style
- Provide examples of good responses
- Set boundaries (what not to do)
- Include formatting instructions
- Specify when to use tools
- Define escalation criteria

**❌ Don't:**
- Be vague or generic
- Make it too long (>2000 chars)
- Include contradictory instructions
- Forget to define tone
- Skip error handling guidance
- Ignore edge cases
- Forget about tool usage

### Dynamic Variables

**Use variables in system prompt:**

```
You are a customer support agent for {{company_name}}.

Current date: {{current_date}}
User timezone: {{user_timezone}}
User name: {{user_name}}

Company information:
- Website: {{company_website}}
- Support email: {{support_email}}
- Business hours: {{business_hours}}
```

**Available Variables:**
- `{{user_name}}` - Current user's name
- `{{user_email}}` - Current user's email
- `{{team_name}}` - User's team name
- `{{current_date}}` - Current date
- `{{current_time}}` - Current time
- `{{company_name}}` - Company name
- Custom variables from context

## LLM Parameters

### Temperature

**Controls randomness:**

```yaml
Temperature: 0.7
Range: 0.0 - 1.0
```

**Guidelines:**
- **0.0 - 0.3**: Deterministic, factual responses
  - Use for: Customer support, technical docs
- **0.4 - 0.7**: Balanced creativity and consistency
  - Use for: General chat, Q&A
- **0.8 - 1.0**: Creative, varied responses
  - Use for: Content creation, brainstorming

### Max Tokens

**Maximum response length:**

```yaml
Max Tokens: 2048
Range: 1 - 128000 (model dependent)
```

**Guidelines:**
- **256-512**: Short responses, quick answers
- **1024-2048**: Standard responses
- **4096+**: Long-form content, detailed explanations

**Note:** Higher values = higher cost

### Top P (Nucleus Sampling)

**Alternative to temperature:**

```yaml
Top P: 0.9
Range: 0.0 - 1.0
```

**Guidelines:**
- **0.9**: Recommended default
- Lower values: More focused responses
- Higher values: More diverse responses

**Note:** Use either temperature OR top_p, not both

### Frequency Penalty

**Reduce repetition:**

```yaml
Frequency Penalty: 0.0
Range: -2.0 - 2.0
```

**Guidelines:**
- **0.0**: No penalty (default)
- **0.5 - 1.0**: Reduce repetition
- **> 1.0**: Strongly discourage repetition

### Presence Penalty

**Encourage new topics:**

```yaml
Presence Penalty: 0.0
Range: -2.0 - 2.0
```

**Guidelines:**
- **0.0**: No penalty (default)
- **0.5 - 1.0**: Encourage topic diversity
- **> 1.0**: Strongly encourage new topics

### Recommended Configurations

**Customer Support:**
```yaml
Temperature: 0.3
Max Tokens: 1024
Top P: 0.9
Frequency Penalty: 0.3
Presence Penalty: 0.0
```

**Content Creation:**
```yaml
Temperature: 0.8
Max Tokens: 4096
Top P: 0.95
Frequency Penalty: 0.5
Presence Penalty: 0.5
```

**Technical Assistant:**
```yaml
Temperature: 0.2
Max Tokens: 2048
Top P: 0.9
Frequency Penalty: 0.0
Presence Penalty: 0.0
```

**General Chat:**
```yaml
Temperature: 0.7
Max Tokens: 2048
Top P: 0.9
Frequency Penalty: 0.3
Presence Penalty: 0.3
```

## Knowledge Base Configuration

### Attach Knowledge Bases

**Add knowledge sources:**

1. Go to **Knowledge Bases** section
2. Click **Add Knowledge Base**
3. Select knowledge bases
4. Configure search settings
5. Save configuration

**Configuration:**

```yaml
Knowledge Bases:
  - Product Documentation
  - FAQ Database
  - Support Tickets Archive

Search Settings:
  Top K: 5
  Score Threshold: 0.7
  Rerank: Enabled
  Search Mode: Hybrid
```

### Search Settings

**Top K:**
- Number of results to retrieve
- Range: 1-20
- Recommended: 3-5

**Score Threshold:**
- Minimum relevance score
- Range: 0.0-1.0
- Recommended: 0.7

**Rerank:**
- Re-score results for better relevance
- Recommended: Enabled

**Search Mode:**
- **Vector**: Semantic search only
- **Keyword**: Full-text search only
- **Hybrid**: Combine both (recommended)

### Knowledge Base Priority

**Set priority for multiple KBs:**

```yaml
Priority Order:
  1. Product Documentation (High)
  2. FAQ Database (Medium)
  3. Support Tickets (Low)
```

**Higher priority KBs:**
- Searched first
- Results weighted higher
- Used for citation

## RAG Configuration

### RAG Modes

**Disabled:**
- No knowledge base retrieval
- Agent uses only training data

**Citation (before_llm):**
- Retrieve documents before LLM call
- Include sources in context
- Agent cites sources in response

**Rewrite (after_llm):**
- Generate response first
- Retrieve documents after
- Rewrite response with sources

**Recommended:** Citation mode for accuracy

### RAG Settings

```yaml
RAG Mode: Citation
Citation Format: Inline
Max Citations: 3
Include Metadata: true
Show Confidence: true
```

**Citation Format:**
- **Inline**: [1], [2], [3] in text
- **Footnotes**: Listed at end
- **Hover**: Show on hover

**Max Citations:**
- Limit number of sources cited
- Range: 1-10
- Recommended: 3-5

## Tool Configuration

### Enable Tools

**Available Tools:**
- Web Search
- Calculator
- Date/Time
- Weather
- Email
- Custom tools

**Configuration:**

```yaml
Enabled Tools:
  - Web Search
  - Calculator
  - Date/Time

Tool Settings:
  Max Tool Calls: 5
  Tool Timeout: 30s
  Parallel Execution: true
```

**Tool Settings:**
- **Max Tool Calls**: Limit per conversation
- **Tool Timeout**: Max execution time
- **Parallel Execution**: Run tools concurrently

### Tool Usage Instructions

**Add to system prompt:**

```
Tool Usage:
- Use web search for current information
- Use calculator for mathematical operations
- Use date/time for scheduling questions
- Always verify tool results before responding
- If a tool fails, explain the error to the user
```

## Advanced Settings

### Streaming

**Enable real-time responses:**

```yaml
Streaming: Enabled
Stream Delay: 0ms
Buffer Size: 1
```

**Benefits:**
- Better user experience
- Faster perceived response time
- Can stop generation early

### Conversation Settings

```yaml
Max Conversation Length: 50 messages
Context Window: 10 messages
Auto-summarize: Enabled
Summary Threshold: 20 messages
```

**Max Conversation Length:**
- Limit total messages
- Prevents context overflow

**Context Window:**
- Recent messages to include
- Older messages summarized

**Auto-summarize:**
- Summarize long conversations
- Reduces token usage

### Response Formatting

```yaml
Format: Markdown
Code Highlighting: Enabled
Link Preview: Enabled
Emoji: Allowed
```

**Format Options:**
- **Plain Text**: No formatting
- **Markdown**: Rich formatting
- **HTML**: Full HTML support

### Safety Settings

```yaml
Content Filtering: Enabled
PII Detection: Enabled
Toxicity Filter: Enabled
Max Retries: 3
```

**Content Filtering:**
- Block inappropriate content
- Configurable sensitivity

**PII Detection:**
- Detect personal information
- Warn or redact

**Toxicity Filter:**
- Block toxic responses
- Configurable threshold

## Testing Configuration

### Test Agent

**Test in configuration:**

1. Click **Test Agent** button
2. Enter test message
3. Review response
4. Check citations and tool usage
5. Adjust configuration if needed
6. Test again

**Test Scenarios:**

```yaml
Test Cases:
  - Simple question
  - Question requiring KB search
  - Question requiring tool usage
  - Complex multi-step question
  - Edge case handling
  - Error scenario
```

### A/B Testing

**Compare configurations:**

1. Create agent variant
2. Configure differently
3. Test both versions
4. Compare metrics:
   - Response quality
   - User satisfaction
   - Response time
   - Cost per conversation
5. Choose best configuration

## Configuration Templates

### Customer Support Template

```yaml
Model: GPT-4 Turbo
Temperature: 0.3
Max Tokens: 1024

System Prompt: |
  You are a helpful customer support agent.
  Always be polite and professional.
  Use the knowledge base to provide accurate information.

Knowledge Bases:
  - Product Documentation
  - FAQ Database

RAG Mode: Citation
Tools:
  - Web Search (for current info)
  - Email (for escalation)
```

### Content Creator Template

```yaml
Model: Claude 3.5 Sonnet
Temperature: 0.8
Max Tokens: 4096

System Prompt: |
  You are a creative content writer.
  Write engaging, original content.
  Use varied vocabulary and sentence structure.

Knowledge Bases:
  - Brand Guidelines
  - Content Examples

RAG Mode: Citation
Tools:
  - Web Search (for research)
```

### Technical Assistant Template

```yaml
Model: GPT-4 Turbo
Temperature: 0.2
Max Tokens: 2048

System Prompt: |
  You are a technical assistant.
  Provide accurate, detailed technical information.
  Include code examples when relevant.

Knowledge Bases:
  - Technical Documentation
  - API Reference

RAG Mode: Citation
Tools:
  - Web Search
  - Calculator
```

## Best Practices

**✅ Do:**
- Test configuration thoroughly
- Start with recommended settings
- Adjust based on feedback
- Monitor performance metrics
- Document configuration choices
- Use templates for consistency
- Version control configurations
- A/B test major changes

**❌ Don't:**
- Use extreme parameter values
- Skip testing
- Ignore user feedback
- Over-complicate system prompt
- Enable unnecessary tools
- Forget about costs
- Change too many things at once
- Deploy without testing

## Troubleshooting

### Poor Response Quality

**Symptoms:**
- Irrelevant responses
- Hallucinations
- Inconsistent behavior

**Solutions:**
1. Lower temperature (0.3-0.5)
2. Improve system prompt clarity
3. Enable RAG with citation mode
4. Add more specific guidelines
5. Increase knowledge base coverage

### High Costs

**Symptoms:**
- Unexpected token usage
- High monthly bills

**Solutions:**
1. Reduce max_tokens
2. Use cheaper model for simple tasks
3. Enable auto-summarization
4. Limit conversation length
5. Optimize system prompt length

### Slow Responses

**Symptoms:**
- Long wait times
- Timeouts

**Solutions:**
1. Use faster model (GPT-3.5, Claude Haiku)
2. Reduce max_tokens
3. Enable streaming
4. Reduce KB search results (top_k)
5. Disable unnecessary tools

## Related Documentation

- [Chatting with Agents](./chatting-with-agents.md) - Using agents
- [Knowledge Base Settings](../knowledge-base/kb-settings.md) - KB configuration
- [Model Management](../../admin-guide/models/model-management.md) - Model admin
- [Tool Management](../../admin-guide/tools/tool-management.md) - Tool admin

---

**Last Updated**: 2026-02-11
