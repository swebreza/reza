import type { Metadata } from 'next'
import { ThemeProvider } from 'next-themes'
import { Analytics } from '@vercel/analytics/next'
import './globals.css'

export const metadata: Metadata = {
  title: {
    default: 'reza - Universal LLM Context Database',
    template: '%s | reza',
  },
  description:
    'Local-first LLM memory for coding agents. Capture project context, searchable chat history, handoffs, and cross-tool threads.',
  keywords: ['LLM', 'AI coding', 'context', 'Claude', 'Cursor', 'Codex', 'Aider', 'session management'],
  openGraph: {
    title: 'reza - Universal LLM Context Database',
    description: 'Local-first searchable memory for AI coding tools.',
    type: 'website',
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="icon" href="/logo.png" type="image/png" />
        <link rel="preload" href="/logo.png" as="image" />
        <link rel="preload" href="/tool-icons/openai.svg" as="image" type="image/svg+xml" />
        <link rel="preload" href="/tool-icons/cursor.svg" as="image" type="image/svg+xml" />
        <link rel="preload" href="/tool-icons/anthropic.svg" as="image" type="image/svg+xml" />
      </head>
      <body className="font-sans antialiased">
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          enableSystem
          disableTransitionOnChange={false}
        >
          {children}
          <Analytics />
        </ThemeProvider>
      </body>
    </html>
  )
}
