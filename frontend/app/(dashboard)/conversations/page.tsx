import { Header } from '@/components/layout/header'
import { ConversationsClient } from './_components'

export default function ConversationsPage() {
  return (
    <div className="flex h-full flex-col">
      <Header />
      <div className="flex flex-1 flex-col gap-4 overflow-auto p-4">
        <ConversationsClient />
      </div>
    </div>
  )
}
