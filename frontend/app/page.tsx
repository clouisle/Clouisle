import { redirect } from 'next/navigation'

export default function Home() {
  // TODO: Check auth status and redirect accordingly
  redirect('/app')
}