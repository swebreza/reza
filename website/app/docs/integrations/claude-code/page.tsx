import { Metadata } from 'next'
import DocPage from '@/components/DocPage'
import { readContent, renderMdx } from '@/lib/mdx'

export const metadata: Metadata = { title: 'Claude Code Integration' }

export default async function ClaudeCodePage() {
  const raw = readContent('integrations/claude-code.md')
  const content = await renderMdx(raw)
  return (
    <DocPage
      title="Claude Code"
      description="Install reza as a native Claude Code skill. Auto-triggers on session start and auto-syncs every response via Stop hook."
      badge="Best integration"
    >
      {content}
    </DocPage>
  )
}
