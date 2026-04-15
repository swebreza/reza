import { Metadata } from 'next'
import DocPage from '@/components/DocPage'
import { readContent, renderMdx } from '@/lib/mdx'

export const metadata: Metadata = { title: 'GitHub Copilot Integration' }

export default async function CopilotPage() {
  const raw = readContent('integrations/copilot.md')
  const content = await renderMdx(raw)
  return (
    <DocPage title="GitHub Copilot" description="Copy the reza context to .github/copilot-instructions.md. Copilot reads this automatically on every workspace open.">
      {content}
    </DocPage>
  )
}
