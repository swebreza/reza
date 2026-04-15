import type { Metadata } from 'next'
import { ThemeProvider } from 'next-themes'
import './globals.css'

export const metadata: Metadata = {
  title: {
    default: 'reza — Universal LLM Context Database',
    template: '%s | reza',
  },
  description:
    'Give any AI coding tool instant awareness of your project. Index once, never re-explain again. Works with Claude, Cursor, Codex, Aider, Kilocode, and more.',
  keywords: ['LLM', 'AI coding', 'context', 'Claude', 'Cursor', 'Codex', 'Aider', 'session management'],
  openGraph: {
    title: 'reza — Universal LLM Context Database',
    description: 'Index your project once. Never re-explain it again.',
    type: 'website',
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="icon" href="/logo.png" type="image/png" />
      </head>
      <body className="font-dm antialiased">
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          enableSystem
          disableTransitionOnChange={false}
        >
          {children}
        </ThemeProvider>
      </body>
    </html>
  )
}
