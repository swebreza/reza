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

const TOOL_COLORS: Record<string, string> = {
  claude: '#d97757',
  cursor: '#9b59b6',
  codex: '#10a37f',
  aider: '#22c55e',
  kilocode: '#f59e0b',
  copilot: '#6366f1',
  continue: '#06b6d4',
  codeium: '#10b981',
  vscode: '#3b82f6',
}

function BrandMark({
  slug,
  color,
  alt,
}: {
  slug: string
  color: string
  alt: string
}) {
  const noHash = color.replace('#', '')
  return (
    <img
      src={`https://cdn.simpleicons.org/${slug}/${noHash}`}
      alt={alt}
      width={14}
      height={14}
      className="h-[14px] w-[14px] shrink-0"
      loading="lazy"
      decoding="async"
    />
  )
}

function CircleMonogram({ label, color }: { label: string; color: string }) {
  return (
    <span
      className="inline-flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold text-white"
      style={{ backgroundColor: color }}
      aria-hidden="true"
    >
      {label}
    </span>
  )
}

function LocalGlyph({
  label,
  color,
  bg = '#0f172a',
}: {
  label: string
  color: string
  bg?: string
}) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-label={label}>
      <rect x="1" y="1" width="14" height="14" rx="4" fill={bg} stroke={color} strokeWidth="1.2" />
      <text
        x="8"
        y="10.2"
        textAnchor="middle"
        fontSize="6.3"
        fontWeight="700"
        fill={color}
        fontFamily="ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
      >
        {label}
      </text>
    </svg>
  )
}

export function ToolLogo({ tool }: { tool: ToolKey }) {
  switch (tool) {
    case 'claude':
      return <BrandMark slug="anthropic" color={TOOL_COLORS.claude} alt="Claude Code" />
    case 'cursor':
      return <BrandMark slug="cursor" color={TOOL_COLORS.cursor} alt="Cursor" />
    case 'codex':
      return <LocalGlyph label="OA" color={TOOL_COLORS.codex} />
    case 'aider':
      return <CircleMonogram label="A" color={TOOL_COLORS.aider} />
    case 'kilocode':
      return <CircleMonogram label="K" color={TOOL_COLORS.kilocode} />
    case 'copilot':
      return <LocalGlyph label="GH" color={TOOL_COLORS.copilot} />
    case 'continue':
      return <LocalGlyph label="CN" color={TOOL_COLORS.continue} />
    case 'codeium':
      return <LocalGlyph label="CI" color={TOOL_COLORS.codeium} />
    case 'vscode':
      return <LocalGlyph label="VS" color={TOOL_COLORS.vscode} />
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
      return <CircleMonogram label="R" color="#475569" />
  }
}

export type { ToolKey }
