import { Metadata } from 'next'
import DocPage from '@/components/DocPage'
import { readContent, renderMdx } from '@/lib/mdx'

export const metadata: Metadata = { title: 'Continue.dev Integration' }

export default async function ContinuePage() {
  const raw = readContent('integrations/continue.md')
  const content = await renderMdx(raw)
  return (
    <DocPage title="Continue.dev" description="Reference the exported context file with @file in Continue chat, or add it to config.json to auto-include on every session.">
      {content}
    </DocPage>
  )
}
