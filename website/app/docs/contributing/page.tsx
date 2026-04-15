import { Metadata } from 'next'
import DocPage from '@/components/DocPage'
import { readContent, renderMdx } from '@/lib/mdx'

export const metadata: Metadata = { title: 'Contributing' }

export default async function ContributingPage() {
  const raw = readContent('CONTRIBUTING.md')
  const content = await renderMdx(raw)
  return (
    <DocPage
      title="Contributing"
      description="Contributions are welcome. See how to set up a development environment, run tests, and add new integrations."
    >
      {content}
    </DocPage>
  )
}
