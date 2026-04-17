import type { ToolKey } from '@/components/ToolLogo'

export interface NavItem {
  label: string
  href: string
  icon?: ToolKey
}

export interface NavGroup {
  label: string
  defaultOpen?: boolean
  items: NavItem[]
}

export const NAV_TREE: NavGroup[] = [
  {
    label: 'Getting Started',
    defaultOpen: true,
    items: [
      { label: 'Introduction', href: '/docs', icon: 'docs' },
      { label: 'Quick Start', href: '/docs/quick-start', icon: 'quickstart' },
      { label: 'Installation', href: '/docs/installation', icon: 'install' },
      { label: 'Configuration', href: '/docs/configuration', icon: 'config' },
    ],
  },
  {
    label: 'Core Concepts',
    defaultOpen: true,
    items: [
      { label: 'How It Works', href: '/docs/how-it-works', icon: 'concepts' },
      { label: 'Sessions & Threads', href: '/docs/sessions', icon: 'sessions' },
      { label: 'Parallel Agents', href: '/docs/parallel-agents', icon: 'parallel' },
    ],
  },
  {
    label: 'CLI Reference',
    defaultOpen: false,
    items: [
      { label: 'All Commands', href: '/docs/cli-reference', icon: 'cli' },
    ],
  },
  {
    label: 'Integrations',
    defaultOpen: false,
    items: [
      { label: 'Overview', href: '/docs/integrations', icon: 'integrations' },
      { label: 'Claude Code', href: '/docs/integrations/claude-code', icon: 'claude' },
      { label: 'Cursor', href: '/docs/integrations/cursor', icon: 'cursor' },
      { label: 'Codex', href: '/docs/integrations/codex', icon: 'codex' },
      { label: 'Aider', href: '/docs/integrations/aider', icon: 'aider' },
      { label: 'Kilocode', href: '/docs/integrations/kilocode', icon: 'kilocode' },
      { label: 'GitHub Copilot', href: '/docs/integrations/copilot', icon: 'copilot' },
      { label: 'Continue.dev', href: '/docs/integrations/continue', icon: 'continue' },
      { label: 'Codeium', href: '/docs/integrations/codeium', icon: 'codeium' },
      { label: 'VS Code Extension', href: '/docs/vscode-extension', icon: 'vscode' },
    ],
  },
  {
    label: 'More',
    defaultOpen: false,
    items: [
      { label: 'Changelog', href: '/docs/changelog', icon: 'changelog' },
      { label: 'Contributing', href: '/docs/contributing', icon: 'contributing' },
    ],
  },
]
