import { Metadata } from 'next'
import Link from 'next/link'
import DocPage from '@/components/DocPage'
import { readContent, renderMdx } from '@/lib/mdx'
import { ToolLogo, type ToolKey } from '@/components/ToolLogo'

export const metadata: Metadata = { title: 'Integrations' }

const TOOLS = [
  { name: 'Claude Code', href: '/docs/integrations/claude-code', icon: 'claude' as ToolKey, desc: 'Native skill plus Stop hook flow', badge: 'Hook' },
  { name: 'Cursor', href: '/docs/integrations/cursor', icon: 'cursor' as ToolKey, desc: 'Project transcript sync and rules' },
  { name: 'Codex', href: '/docs/integrations/codex', icon: 'codex' as ToolKey, desc: 'Local rollout sync and handoff commands' },
  { name: 'Aider', href: '/docs/integrations/aider', icon: 'aider' as ToolKey, desc: '.aider.chat.history.md ingestion' },
  { name: 'Kilocode', href: '/docs/integrations/kilocode', icon: 'kilocode' as ToolKey, desc: 'Rules file and drop-zone fallback' },
  { name: 'GitHub Copilot', href: '/docs/integrations/copilot', icon: 'copilot' as ToolKey, desc: 'Copilot instructions plus context export' },
  { name: 'Continue.dev', href: '/docs/integrations/continue', icon: 'continue' as ToolKey, desc: 'Export or config-driven context' },
  { name: 'Codeium / Windsurf', href: '/docs/integrations/codeium', icon: 'codeium' as ToolKey, desc: 'Open context file in the editor' },
  { name: 'VS Code Extension', href: '/docs/vscode-extension', icon: 'vscode' as ToolKey, desc: 'Search and graph UI inside VS Code' },
]

export default async function IntegrationsPage() {
  const raw = readContent('integrations/README.md')
  const content = await renderMdx(raw)

  return (
    <DocPage
      title="Integrations"
      description="Connect Reza memory to coding agents through the CLI, hooks, local transcript adapters, and drop-zone ingestion."
    >
      <div className="not-prose mb-12 grid gap-4 sm:grid-cols-2">
        {TOOLS.map((tool) => (
          <Link
            key={tool.href}
            href={tool.href}
            className="group rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] p-5 transition-colors hover:border-teal-DEFAULT/45"
          >
            <div className="flex items-start gap-4">
              <span className="mt-0.5 inline-flex h-10 w-10 items-center justify-center rounded-lg border border-[var(--border)] bg-[var(--surface)]">
                <ToolLogo tool={tool.icon} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="mb-1 flex items-center gap-2">
                  <span className="text-sm font-semibold text-white">{tool.name}</span>
                  {tool.badge && (
                    <span className="rounded-md bg-teal-DEFAULT/15 px-2 py-0.5 text-[10px] font-medium text-teal-DEFAULT">
                      {tool.badge}
                    </span>
                  )}
                </div>
                <p className="text-xs leading-6 text-slate-500">{tool.desc}</p>
              </div>
            </div>
          </Link>
        ))}
      </div>

      {content}
    </DocPage>
  )
}
