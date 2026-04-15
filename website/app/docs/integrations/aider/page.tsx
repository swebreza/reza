import { Metadata } from 'next'
import DocPage from '@/components/DocPage'
import { readContent, renderMdx } from '@/lib/mdx'

export const metadata: Metadata = { title: 'Aider Integration' }

export default async function AiderPage() {
  const raw = readContent('integrations/aider.md')
  const content = await renderMdx(raw)
  return (
    <DocPage title="Aider" description="Use reza with Aider via --read to inject full project context into every session. Supports auto-sync via file watcher.">
      {content}
    </DocPage>
  )
}
