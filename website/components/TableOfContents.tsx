'use client'

import { useEffect, useState } from 'react'
import clsx from 'clsx'

interface Heading {
  id: string
  text: string
  level: number
}

export default function TableOfContents() {
  const [headings, setHeadings] = useState<Heading[]>([])
  const [active, setActive] = useState<string>('')

  useEffect(() => {
    const els = document.querySelectorAll('article h2, article h3')
    const found: Heading[] = Array.from(els).map((el) => ({
      id: el.id,
      text: el.textContent ?? '',
      level: parseInt(el.tagName[1]),
    }))
    setHeadings(found)

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) setActive(entry.target.id)
        })
      },
      { rootMargin: '-64px 0px -60% 0px', threshold: 0 }
    )
    els.forEach((el) => observer.observe(el))
    return () => observer.disconnect()
  }, [])

  if (headings.length === 0) return null

  return (
    <nav className="w-52 flex-shrink-0 sticky top-16 h-[calc(100vh-4rem)] overflow-y-auto py-6 pl-4 hidden xl:block">
      <p className="text-[11px] font-bold uppercase tracking-widest text-slate-500 dark:text-slate-600 mb-4 px-3">
        On this page
      </p>
      <ul className="space-y-1">
        {headings.map((h) => (
          <li key={h.id}>
            <a
              href={`#${h.id}`}
              className={clsx(
                'block text-xs py-1 transition-colors rounded-md',
                h.level === 3 ? 'pl-6 pr-3' : 'px-3',
                active === h.id
                  ? 'text-teal-DEFAULT font-medium'
                  : 'text-slate-500 hover:text-slate-300 dark:text-slate-600 dark:hover:text-slate-400'
              )}
            >
              {h.text}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  )
}
