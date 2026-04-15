import { Metadata } from 'next'
import DocPage from '@/components/DocPage'
import { readContent, renderMdx } from '@/lib/mdx'

export const metadata: Metadata = { title: 'Changelog' }

export default async function ChangelogPage() {
  const raw = readContent('CHANGELOG.md')
  const content = await renderMdx(raw)
  return (
    <DocPage
      title="Changelog"
      description="All notable changes to reza are documented here. Follows Keep a Changelog and Semantic Versioning."
    >
      {content}
    </DocPage>
  )
}
