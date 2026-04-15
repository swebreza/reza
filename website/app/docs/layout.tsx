import Navbar from '@/components/Navbar'
import Sidebar from '@/components/Sidebar'
import TableOfContents from '@/components/TableOfContents'

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-[#0b0f16] dark:bg-[#0b0f16] text-white">
      <Navbar />
      <div className="max-w-[1400px] mx-auto flex pt-16">
        <Sidebar />
        <main className="flex-1 min-w-0 px-6 lg:px-12 py-10">
          {children}
        </main>
        <TableOfContents />
      </div>
    </div>
  )
}
