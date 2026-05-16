import { LocaleSwitcher } from '@/components/locale-switcher'
import type { AuthPageLayout } from '@/lib/api/site-settings'

interface AuthLayoutShellProps {
  children: React.ReactNode
  layout: AuthPageLayout
  siteName: string
  siteDescription: string
}

function AuthPreviewPanel({ siteName }: Pick<AuthLayoutShellProps, 'siteName'>) {
  return (
    <aside className="relative hidden min-h-screen flex-1 overflow-hidden bg-muted/45 dark:bg-muted/25 lg:block">
      <img
        src="/clouisle.png"
        alt={siteName}
        className="absolute left-12 top-40 max-w-none rounded-2xl border border-slate-300/80 shadow-[0_32px_90px_rgba(15,23,42,0.28)] dark:border-white/20 dark:shadow-[0_32px_100px_rgba(0,0,0,0.78)] xl:left-16 xl:top-48"
        style={{ height: '80vh', width: 'auto' }}
      />
    </aside>
  )
}

export function AuthLayoutShell({
  children,
  layout,
  siteName,
}: AuthLayoutShellProps) {
  const isSplit = layout === 'split'

  if (!isSplit) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-muted/50">
        <div className="fixed right-4 top-4 z-10">
          <LocaleSwitcher />
        </div>
        <div className="w-full max-w-md p-4">
          {children}
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background lg:flex">
      <div className="fixed right-4 top-4 z-10">
        <LocaleSwitcher />
      </div>
      <main className="flex min-h-screen w-full items-center justify-center bg-background px-4 py-12 lg:w-[48%] lg:px-10 lg:pr-16 xl:pr-20">
        <div className="w-full max-w-md lg:mr-24 xl:mr-32">
          {children}
        </div>
      </main>
      <AuthPreviewPanel siteName={siteName} />
    </div>
  )
}
