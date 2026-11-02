export interface GrokBallEngine {
  readonly emotionId: string | null
  setEmotion(id: string): boolean
  setGaze(x: number, y: number): void
  clearGaze(): void
  spin(): void
  destroy(): void
}

export interface GrokBallApi {
  create(target: Element, options: { emotion: string; color: string; eyeColor: string; autostart: boolean }): GrokBallEngine
}

export function initializeGrokBall(): GrokBallApi
