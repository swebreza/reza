import Navbar from '@/components/Navbar'
import Sidebar from '@/components/Sidebar'
import TableOfContents from '@/components/TableOfContents'

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-[#0b1220] text-white">
      <Navbar />
      <div className="max-w-[1500px] mx-auto flex pt-16 px-4 md:px-8 xl:px-10">
        <Sidebar />
        <main className="flex-1 min-w-0 px-4 md:px-8 xl:px-12 py-12">
          {children}
        </main>
        <TableOfContents />
      </div>
    </div>
  )
}
