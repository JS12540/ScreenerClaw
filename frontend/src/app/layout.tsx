import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'ScreenerClaw - AI Indian Stock Screener',
  description:
    'AI-powered stock screening for Indian markets. Discover undervalued gems, analyse fundamentals, and get deep valuation insights — all in natural language.',
  keywords: ['Indian stocks', 'NSE', 'BSE', 'stock screener', 'AI', 'fundamental analysis', 'valuation'],
  authors: [{ name: 'ScreenerClaw' }],
  themeColor: '#0f172a',
  openGraph: {
    title: 'ScreenerClaw - AI Indian Stock Screener',
    description: 'AI-powered stock screening for Indian markets.',
    type: 'website',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className={`${inter.variable} dark`}>
      <body className="bg-slate-900 text-slate-100 font-sans antialiased min-h-screen">
        {children}
      </body>
    </html>
  )
}
