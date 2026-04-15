import { ReactNode } from 'react'

interface Props {
  title: string
  description?: string
  children: ReactNode
  badge?: string
}

export default function DocPage({ title, description, children, badge }: Props) {
  return (
    <article className="max-w-3xl">
      {/* Page header */}
      <header className="mb-10 pb-8 border-b border-[#1e2730]">
        {badge && (
          <span className="inline-block mb-3 px-3 py-1 rounded-full text-xs font-semibold border border-teal-DEFAULT/30 bg-teal-DEFAULT/10 text-teal-DEFAULT">
            {badge}
          </span>
        )}
        <h1 className="font-syne font-800 text-4xl md:text-5xl tracking-tight text-white mb-4">
          {title.split(' ').map((word, i) =>
            i === 0
              ? <span key={i} className="gradient-text">{word} </span>
              : <span key={i}>{word} </span>
          )}
        </h1>
        {description && (
          <p className="text-slate-400 text-lg leading-relaxed">{description}</p>
        )}
      </header>

      {/* MDX content */}
      <div className="
        prose prose-invert max-w-none
        prose-headings:font-syne prose-headings:tracking-tight prose-headings:font-700
        prose-h2:text-2xl prose-h2:mt-12 prose-h2:mb-4 prose-h2:text-white
        prose-h3:text-xl prose-h3:mt-8 prose-h3:mb-3 prose-h3:text-white
        prose-h4:text-base prose-h4:mt-6 prose-h4:mb-2 prose-h4:text-slate-200
        prose-p:text-slate-400 prose-p:leading-relaxed
        prose-li:text-slate-400
        prose-strong:text-white prose-strong:font-600
        prose-a:text-teal-DEFAULT prose-a:no-underline hover:prose-a:text-sky-brand
        prose-blockquote:border-teal-DEFAULT prose-blockquote:bg-teal-DEFAULT/5
        prose-blockquote:not-italic prose-blockquote:rounded-r-lg prose-blockquote:text-slate-300
        prose-code:text-teal-DEFAULT prose-code:bg-teal-DEFAULT/10 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded
        prose-code:before:content-none prose-code:after:content-none
        prose-pre:bg-[#0d1117] prose-pre:border prose-pre:border-[#1e2730] prose-pre:rounded-xl
        prose-table:text-sm prose-th:text-slate-400 prose-th:font-600
        prose-td:text-slate-400 prose-tr:border-[#1e2730]
      ">
        {children}
      </div>
    </article>
  )
}
