import fs from 'fs'
import path from 'path'
import { compileMDX } from 'next-mdx-remote/rsc'
import remarkGfm from 'remark-gfm'
import rehypePrettyCode from 'rehype-pretty-code'
import rehypeSlug from 'rehype-slug'
import rehypeAutolinkHeadings from 'rehype-autolink-headings'

const CONTENT_DIR = path.join(process.cwd(), 'content')

export function readContent(relativePath: string): string {
  const fullPath = path.join(CONTENT_DIR, relativePath)
  return fs.readFileSync(fullPath, 'utf8')
}

export function extractSection(
  content: string,
  startHeading: string,
  stopHeadings?: string[]
): string {
  const lines = content.split('\n')
  let capturing = false
  const result: string[] = []

  for (const line of lines) {
    if (line.startsWith('#') && line.includes(startHeading)) {
      capturing = true
    } else if (capturing && stopHeadings) {
      const isStop = stopHeadings.some((h) => line.startsWith('#') && line.includes(h))
      if (isStop) break
    }
    if (capturing) result.push(line)
  }

  return result.join('\n')
}

const prettyCodeOptions = {
  theme: 'github-dark',
  keepBackground: true,
  onVisitLine(node: { children: { type: string; value: string }[] }) {
    if (node.children.length === 0) {
      node.children = [{ type: 'text', value: ' ' }]
    }
  },
}

export async function renderMdx(source: string) {
  // Strip YAML frontmatter (--- ... ---) from SKILL.md etc.
  const stripped = source.replace(/^---[\s\S]*?---\n?/, '')

  const { content } = await compileMDX({
    source: stripped,
    options: {
      mdxOptions: {
        remarkPlugins: [remarkGfm],
        rehypePlugins: [
          [rehypePrettyCode as never, prettyCodeOptions],
          rehypeSlug,
          [
            rehypeAutolinkHeadings,
            {
              behavior: 'wrap',
              properties: {
                className: ['anchor'],
              },
            },
          ],
        ],
        format: 'md',
      },
    },
  })
  return content
}
