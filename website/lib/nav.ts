export interface NavItem {
  label: string
  href: string
  icon?: string
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
      { label: 'Introduction', href: '/docs', icon: '📖' },
      { label: 'Quick Start', href: '/docs/quick-start', icon: '⚡' },
      { label: 'Installation', href: '/docs/installation', icon: '📦' },
      { label: 'Configuration', href: '/docs/configuration', icon: '⚙️' },
    ],
  },
  {
    label: 'Core Concepts',
    defaultOpen: true,
    items: [
      { label: 'How It Works', href: '/docs/how-it-works', icon: '🧠' },
      { label: 'Sessions & Threads', href: '/docs/sessions', icon: '🔗' },
      { label: 'Parallel Agents', href: '/docs/parallel-agents', icon: '⚡' },
    ],
  },
  {
    label: 'CLI Reference',
    defaultOpen: false,
    items: [
      { label: 'All Commands', href: '/docs/cli-reference', icon: '💻' },
    ],
  },
  {
    label: 'Integrations',
    defaultOpen: false,
    items: [
      { label: 'Overview', href: '/docs/integrations', icon: '🔌' },
      { label: 'Claude Code', href: '/docs/integrations/claude-code', icon: '🟠' },
      { label: 'Cursor', href: '/docs/integrations/cursor', icon: '🟣' },
      { label: 'Codex', href: '/docs/integrations/codex', icon: '🔵' },
      { label: 'Aider', href: '/docs/integrations/aider', icon: '🟢' },
      { label: 'Kilocode', href: '/docs/integrations/kilocode', icon: '🟡' },
      { label: 'GitHub Copilot', href: '/docs/integrations/copilot', icon: '🔷' },
      { label: 'Continue.dev', href: '/docs/integrations/continue', icon: '🩵' },
      { label: 'Codeium', href: '/docs/integrations/codeium', icon: '💚' },
      { label: 'VS Code Extension', href: '/docs/vscode-extension', icon: '🔷' },
    ],
  },
  {
    label: 'More',
    defaultOpen: false,
    items: [
      { label: 'Changelog', href: '/docs/changelog', icon: '📋' },
      { label: 'Contributing', href: '/docs/contributing', icon: '🤝' },
    ],
  },
]
