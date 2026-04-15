import { Metadata } from 'next'
import DocPage from '@/components/DocPage'
import { readContent, renderMdx, extractSection } from '@/lib/mdx'
import Link from 'next/link'
import { ArrowRight } from 'lucide-react'

export const metadata: Metadata = { title: 'Introduction' }

export default async function DocsIntroPage() {
  const raw = readContent('README.md')
  const problemSection = extractSection(raw, 'The Problem', ['The Solution', 'Quick Start'])
  const solutionSection = extractSection(raw, 'The Solution', ['Quick Start', 'Install as'])
  const combined = `${problemSection}\n\n${solutionSection}`
  const content = await renderMdx(combined)

  return (
    <DocPage
      title="Introduction"
      description="reza is a Universal LLM Context Database — give any AI coding tool instant awareness of your project."
    >
      {content}

      {/* Quick nav to next pages */}
      <div className="mt-16 pt-8 border-t border-[#1e2730] grid sm:grid-cols-2 gap-4 not-prose">
        <Link href="/docs/quick-start"
          className="group flex items-center justify-between p-5 rounded-xl border border-[#1e2730] hover:border-teal-DEFAULT/40 bg-[#0d1117] transition-colors">
          <div>
            <div className="text-xs text-teal-DEFAULT font-semibold mb-1">Next</div>
            <div className="font-syne font-600 text-white">Quick Start</div>
            <div className="text-xs text-slate-500 mt-0.5">Up and running in 2 minutes</div>
          </div>
          <ArrowRight size={16} className="text-slate-600 group-hover:text-teal-DEFAULT transition-colors" />
        </Link>
        <Link href="/docs/how-it-works"
          className="group flex items-center justify-between p-5 rounded-xl border border-[#1e2730] hover:border-teal-DEFAULT/40 bg-[#0d1117] transition-colors">
          <div>
            <div className="text-xs text-slate-500 font-semibold mb-1">Concept</div>
            <div className="font-syne font-600 text-white">How It Works</div>
            <div className="text-xs text-slate-500 mt-0.5">Database schema + sync mechanisms</div>
          </div>
          <ArrowRight size={16} className="text-slate-600 group-hover:text-teal-DEFAULT transition-colors" />
        </Link>
      </div>
    </DocPage>
  )
}
