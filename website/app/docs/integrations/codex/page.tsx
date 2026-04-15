import { Metadata } from 'next'
import DocPage from '@/components/DocPage'
import { readContent, renderMdx } from '@/lib/mdx'

export const metadata: Metadata = { title: 'OpenAI Codex Integration' }

export default async function CodexPage() {
  const raw = readContent('integrations/codex.md')
  const content = await renderMdx(raw)
  return (
    <DocPage title="OpenAI Codex" description="Inject reza context via --system-prompt or a shell alias. Works with Codex CLI and Codex Desktop.">
      {content}
    </DocPage>
  )
}
