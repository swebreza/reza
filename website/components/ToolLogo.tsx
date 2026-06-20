import { Bot, Braces, Cpu, FileCode2, Github, TerminalSquare } from 'lucide-react'

type ToolKey =
  | 'claude'
  | 'cursor'
  | 'codex'
  | 'aider'
  | 'kilocode'
  | 'copilot'
  | 'continue'
  | 'codeium'
  | 'vscode'
  | 'docs'
  | 'quickstart'
  | 'install'
  | 'config'
  | 'concepts'
  | 'sessions'
  | 'parallel'
  | 'cli'
  | 'integrations'
  | 'changelog'
  | 'contributing'

const TOOL_ICONS: Partial<Record<ToolKey, { src: string; alt: string }>> = {
  claude: { src: '/tool-icons/anthropic.svg', alt: 'Claude Code' },
  cursor: { src: '/tool-icons/cursor.svg', alt: 'Cursor' },
  codex: { src: '/tool-icons/openai.svg', alt: 'Codex' },
  aider: { src: '/tool-icons/aider.svg', alt: 'Aider' },
  kilocode: { src: '/tool-icons/kilocode.svg', alt: 'Kilocode' },
  copilot: { src: '/tool-icons/copilot.svg', alt: 'GitHub Copilot' },
  continue: { src: '/tool-icons/continue.svg', alt: 'Continue' },
  codeium: { src: '/tool-icons/codeium.svg', alt: 'Codeium' },
  vscode: { src: '/tool-icons/vscode.svg', alt: 'Visual Studio Code' },
}

function LocalIcon({ src, alt }: { src: string; alt: string }) {
  return (
    <img
      src={src}
      alt={alt}
      width={18}
      height={18}
      className="h-[18px] w-[18px] shrink-0"
      loading="lazy"
      decoding="async"
    />
  )
}

export function ToolLogo({ tool }: { tool: ToolKey }) {
  const icon = TOOL_ICONS[tool]
  if (icon) return <LocalIcon src={icon.src} alt={icon.alt} />

  switch (tool) {
    case 'docs':
      return <FileCode2 size={14} className="text-slate-300" aria-hidden="true" />
    case 'quickstart':
      return <TerminalSquare size={14} className="text-teal-300" aria-hidden="true" />
    case 'install':
      return <Bot size={14} className="text-sky-300" aria-hidden="true" />
    case 'config':
      return <Cpu size={14} className="text-slate-300" aria-hidden="true" />
    case 'concepts':
      return <Bot size={14} className="text-violet-300" aria-hidden="true" />
    case 'sessions':
      return <Braces size={14} className="text-sky-300" aria-hidden="true" />
    case 'parallel':
      return <Cpu size={14} className="text-amber-300" aria-hidden="true" />
    case 'cli':
      return <TerminalSquare size={14} className="text-emerald-300" aria-hidden="true" />
    case 'integrations':
      return <Bot size={14} className="text-fuchsia-300" aria-hidden="true" />
    case 'changelog':
      return <FileCode2 size={14} className="text-slate-300" aria-hidden="true" />
    case 'contributing':
      return <Github size={14} className="text-slate-300" aria-hidden="true" />
    default:
      return <FileCode2 size={14} className="text-slate-300" aria-hidden="true" />
  }
}

export type { ToolKey }
