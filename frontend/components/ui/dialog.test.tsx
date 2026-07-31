import { beforeEach, describe, expect, mock, test } from "bun:test"

type Props = Record<string, unknown>
type Node = { type: unknown; props: Props }
type Effect = () => void | (() => void)

const jsx = (type: unknown, props: Props = {}) => ({ type, props })
const primitive = (name: string) => function Primitive() { return name }
const Root = primitive("Root")
const Trigger = primitive("Trigger")
const Portal = primitive("Portal")
const Close = primitive("Close")
const Backdrop = primitive("Backdrop")
const Popup = primitive("Popup")
const Title = primitive("Title")
const Description = primitive("Description")
const Button = primitive("Button")
const XIcon = primitive("XIcon")

let states: unknown[] = []
let stateIndex = 0
let effects: Effect[] = []
const rafCallbacks: FrameRequestCallback[] = []
const timeoutCallbacks: TimerHandler[] = []
const cancelAnimationFrameMock = mock(() => {})
const clearTimeoutMock = mock(() => {})

mock.module("react/jsx-runtime", () => ({ jsx, jsxs: jsx, Fragment: Symbol.for("react.fragment") }))
mock.module("react/jsx-dev-runtime", () => ({ jsxDEV: jsx, Fragment: Symbol.for("react.fragment") }))
mock.module("react", () => ({
  useState: <T,>(initial: T) => {
    const index = stateIndex++
    states[index] ??= initial
    return [states[index] as T, (value: T) => { states[index] = value }] as const
  },
  useEffect: (effect: Effect) => effects.push(effect),
}))
mock.module("@base-ui/react/dialog", () => ({
  Dialog: { Root, Trigger, Portal, Close, Backdrop, Popup, Title, Description },
}))
mock.module("@/lib/utils", () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(" ") }))
mock.module("@/components/ui/button", () => ({ Button }))
mock.module("lucide-react", () => ({ XIcon }))

const dialog = await import("./dialog")

function renderContent(props: Props = {}): Node {
  stateIndex = 0
  effects = []
  return dialog.DialogContent(props) as Node
}

beforeEach(() => {
  states = []
  effects = []
  rafCallbacks.length = 0
  timeoutCallbacks.length = 0
  cancelAnimationFrameMock.mockClear()
  clearTimeoutMock.mockClear()
  globalThis.requestAnimationFrame = ((callback: FrameRequestCallback) => {
    rafCallbacks.push(callback)
    return 7
  }) as typeof requestAnimationFrame
  globalThis.cancelAnimationFrame = cancelAnimationFrameMock
  globalThis.window = {
    setTimeout: (callback: TimerHandler) => {
      timeoutCallbacks.push(callback)
      return 9
    },
    clearTimeout: clearTimeoutMock,
  } as unknown as Window & typeof globalThis
})

describe("dialog wrappers", () => {
  test("forwards slots, classes, and custom props", () => {
    expect(dialog.Dialog({ open: true } as never)).toEqual(jsx(Root, { "data-slot": "dialog", open: true }))
    expect(dialog.DialogTrigger({ className: "custom", disabled: true } as never)).toEqual(
      jsx(Trigger, { "data-slot": "dialog-trigger", className: "cursor-pointer custom", disabled: true }),
    )
    expect(dialog.DialogPortal({ keepMounted: true } as never)).toEqual(jsx(Portal, { "data-slot": "dialog-portal", keepMounted: true }))
    expect(dialog.DialogClose({ disabled: true } as never)).toEqual(jsx(Close, { "data-slot": "dialog-close", disabled: true }))
    expect(dialog.DialogOverlay({ className: "custom" } as never).props).toMatchObject({
      "data-slot": "dialog-overlay",
      className: expect.stringContaining("custom"),
    })
    expect(dialog.DialogHeader({ className: "custom" }).props.className).toContain("custom")
    expect(dialog.DialogTitle({ className: "custom" } as never).props.className).toContain("custom")
    expect(dialog.DialogDescription({ className: "custom" } as never).props.className).toContain("custom")
  })

  test("renders optional content and footer close controls", () => {
    const content = renderContent({ children: "body" })
    const contentChildren = content.props.children as Node[]
    expect(contentChildren[0].type).toBe(dialog.DialogOverlay)
    expect(contentChildren[1].props.className).toContain("grid-cols-[minmax(0,1fr)]")
    expect((contentChildren[1].props.children as unknown[])[0]).toBe("body")
    expect((contentChildren[1].props.children as Node[])[1].type).toBe(Close)

    const bare = renderContent({ children: "body", hideOverlay: true, showCloseButton: false })
    expect((bare.props.children as unknown[])[0]).toBe(false)
    expect((bare.props.children as Node[])[1].props.children).toEqual(["body", false])

    const footer = dialog.DialogFooter({ children: "action", showCloseButton: true }) as Node
    expect((footer.props.children as Node[])[1]).toMatchObject({ type: Close, props: { children: "Close" } })
    expect((dialog.DialogFooter({ children: "action" }) as Node).props.children).toEqual(["action", false])
  })
})

describe("animated overlay callbacks", () => {
  test("shows on open, enables transitions on the next frame, and cancels the frame", () => {
    renderContent({ open: true, disableOverlayAnimation: true })
    const cleanup = effects[0]() as () => void
    expect(states).toEqual([true, false])

    rafCallbacks[0](0)
    expect(states).toEqual([true, true])
    cleanup()
    expect(cancelAnimationFrameMock).toHaveBeenCalledWith(7)

    const tree = renderContent({ open: true, disableOverlayAnimation: true, overlayClassName: "overlay" })
    const overlay = (tree.props.children as Node[])[0]
    expect(overlay.props.className).toContain("opacity-100")
    expect(overlay.props.className).toContain("overlay")
  })

  test("delays hiding on close, clears the timer, and hides immediately when requested", () => {
    states = [true, true]
    renderContent({ open: false, disableOverlayAnimation: true })
    const cleanup = effects[0]() as () => void
    expect(timeoutCallbacks).toHaveLength(1)
    cleanup()
    expect(clearTimeoutMock).toHaveBeenCalledWith(9)

    ;(timeoutCallbacks[0] as () => void)()
    expect(states).toEqual([false, false])
    expect((renderContent({ open: false, disableOverlayAnimation: true }).props.children as unknown[])[0]).toBe(false)

    states = [true, true]
    renderContent({ hideOverlay: true })
    expect(effects[0]()).toBeUndefined()
    expect(states).toEqual([false, true])
  })
})
