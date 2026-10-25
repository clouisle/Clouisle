import type { ComponentType, SVGProps } from 'react'

import { AnthropicIcon } from './anthropic'
import { AzureIcon } from './azure'
import { BaichuanIcon } from './baichuan'
import { BaaiIcon } from './baai'
import { DeepSeekIcon } from './deepseek'
import { GoogleIcon } from './google'
import { GatewayIcon } from './gateway'
import { KlingIcon } from './kling'
import { LongCatIcon } from './longcat'
import { LumaIcon } from './luma'
import { MidjourneyIcon } from './midjourney'
import { MinimaxIcon } from './minimax'
import { MoonshotIcon } from './moonshot'
import { OllamaIcon } from './ollama'
import { OpenAIIcon } from './openai'
import { PikaIcon } from './pika'
import { QwenIcon } from './qwen'
import { RunwayIcon } from './runway'
import { SiliconCloudIcon } from './siliconcloud'
import { StabilityIcon } from './stability'
import { TypeSafeIcon } from './typesafe'
import { VolcengineIcon } from './volcengine'
import { XaiIcon } from './xai'
import { ZhipuIcon } from './zhipu'

// Vendored from lobehub/lobe-icons v6.9.1 (MIT). See ./LICENSE.
export type ProviderMark = ComponentType<
  SVGProps<SVGSVGElement> & { size?: number | string }
>

export const PROVIDER_MARKS: Record<string, ProviderMark> = {
  openai: OpenAIIcon,
  anthropic: AnthropicIcon,
  google: GoogleIcon,
  xai: XaiIcon,
  azure: AzureIcon,
  deepseek: DeepSeekIcon,
  moonshot: MoonshotIcon,
  zhipu: ZhipuIcon,
  qwen: QwenIcon,
  baichuan: BaichuanIcon,
  baai: BaaiIcon,
  minimax: MinimaxIcon,
  volcengine: VolcengineIcon,
  siliconcloud: SiliconCloudIcon,
  ollama: OllamaIcon,
  runway: RunwayIcon,
  pika: PikaIcon,
  luma: LumaIcon,
  kling: KlingIcon,
  longcat: LongCatIcon,
  stability: StabilityIcon,
  midjourney: MidjourneyIcon,
  typesafe: TypeSafeIcon,
  gateway: GatewayIcon,
}
