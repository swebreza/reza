import { Metadata } from 'next'
import DocPage from '@/components/DocPage'
import { readContent, renderMdx, extractSection } from '@/lib/mdx'

export const metadata: Metadata = { title: 'How It Works' }

export default async function HowItWorksPage() {
  const raw = readContent('README.md')
  const section = extractSection(raw, 'How It Works', ['Installation', 'Per-Project Setup'])
  const content = await renderMdx(section)

  return (
    <DocPage
      title="How It Works"
      description="reza stores your project's structure, sessions, and conversation history in a local SQLite database."
    >
      {content}
    </DocPage>
  )
}
