'use client'

import { useState, useRef, useEffect } from 'react'
import { analyze, getLLMProviders, AnalyzeResponse, LLMProviderInfo } from '@/lib/api'

// ─── Loading messages (cycle through while waiting) ───────────────────────────

const LOADING_STEPS = [
  '🔐 Logging into Screener.in...',
  '🔍 Routing your query...',
  '📊 Scraping financial data...',
  '🧮 Deriving valuation assumptions...',
  '💰 Running Graham, DCF, Greenwald models...',
  '🏢 Analysing business & moat...',
  '🎯 Computing final verdict...',
  '📝 Generating investment report...',
]

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmtNum(n: number | null | undefined, suffix = ''): string {
  if (n == null) return '—'
  return n.toLocaleString('en-IN') + suffix
}

function fmtCr(n: number | null | undefined): string {
  if (n == null) return '—'
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(1)}L Cr`
  return `₹${n.toLocaleString('en-IN')} Cr`
}

// ─── Simple Markdown renderer ──────────────────────────────────────────────────

function MarkdownReport({ markdown }: { markdown: string }) {
  const lines = markdown.split('\n')
  const elements: React.ReactNode[] = []
  let inTable = false
  let tableRows: string[][] = []
  let tableKey = 0

  function flushTable() {
    if (tableRows.length < 2) {
      tableRows = []
      inTable = false
      return
    }
    const header = tableRows[0]
    const body = tableRows.slice(2) // skip separator row
    elements.push(
      <div key={`tbl-${tableKey++}`} className="overflow-x-auto my-4">
        <table className="min-w-full text-sm border-collapse">
          <thead>
            <tr className="bg-slate-700">
              {header.map((cell, i) => (
                <th key={i} className="px-3 py-2 text-left font-semibold text-slate-200 border border-slate-600 whitespace-nowrap">
                  {cell.trim().replace(/\*\*/g, '')}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {body.map((row, ri) => (
              <tr key={ri} className={ri % 2 === 0 ? 'bg-slate-800' : 'bg-slate-800/60'}>
                {row.map((cell, ci) => (
                  <td key={ci} className="px-3 py-1.5 text-slate-300 border border-slate-700">
                    <span dangerouslySetInnerHTML={{ __html: renderInline(cell.trim()) }} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
    tableRows = []
    inTable = false
  }

  function renderInline(text: string): string {
    return text
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/`(.+?)`/g, '<code class="bg-slate-700 px-1 rounded text-emerald-300">$1</code>')
      .replace(/⚠️/g, '<span class="text-amber-400">⚠️</span>')
      .replace(/✓/g, '<span class="text-emerald-400">✓</span>')
      .replace(/✗/g, '<span class="text-red-400">✗</span>')
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]

    // Table row
    if (line.startsWith('|')) {
      if (!inTable) inTable = true
      const cells = line.split('|').filter((_, idx, arr) => idx > 0 && idx < arr.length - 1)
      tableRows.push(cells)
      continue
    }

    // Flush table if we exit it
    if (inTable) {
      flushTable()
    }

    if (!line.trim()) {
      elements.push(<div key={i} className="h-3" />)
      continue
    }

    if (line.startsWith('# ')) {
      elements.push(
        <h1 key={i} className="text-2xl font-bold text-white mt-6 mb-2 pb-2 border-b border-slate-600">
          {line.slice(2)}
        </h1>
      )
    } else if (line.startsWith('## ')) {
      elements.push(
        <h2 key={i} className="text-xl font-semibold text-emerald-400 mt-6 mb-2">
          {line.slice(3)}
        </h2>
      )
    } else if (line.startsWith('### ')) {
      elements.push(
        <h3 key={i} className="text-base font-semibold text-slate-200 mt-4 mb-1">
          {line.slice(4)}
        </h3>
      )
    } else if (line.startsWith('> ')) {
      elements.push(
        <blockquote key={i} className="border-l-4 border-emerald-500 pl-4 py-1 my-2 text-slate-300 italic bg-slate-800/40 rounded-r">
          <span dangerouslySetInnerHTML={{ __html: renderInline(line.slice(2)) }} />
        </blockquote>
      )
    } else if (line.startsWith('- ') || line.startsWith('* ')) {
      elements.push(
        <li key={i} className="ml-4 text-slate-300 list-disc"
          dangerouslySetInnerHTML={{ __html: renderInline(line.slice(2)) }}
        />
      )
    } else if (line.startsWith('---')) {
      elements.push(<hr key={i} className="border-slate-700 my-4" />)
    } else if (line.startsWith('**') && line.endsWith('**') && line.length > 4) {
      elements.push(
        <p key={i} className="font-bold text-slate-200 mt-3"
          dangerouslySetInnerHTML={{ __html: renderInline(line) }}
        />
      )
    } else {
      elements.push(
        <p key={i} className="text-slate-300 leading-relaxed"
          dangerouslySetInnerHTML={{ __html: renderInline(line) }}
        />
      )
    }
  }

  if (inTable) flushTable()

  return <div className="report-content">{elements}</div>
}

// ─── Screening Results Table ───────────────────────────────────────────────────

function ScreeningTable({ results, query }: { results: any[]; query: string }) {
  return (
    <div>
      <h2 className="text-xl font-semibold text-emerald-400 mb-1">Screening Results</h2>
      <p className="text-slate-400 text-sm mb-4">Query: <span className="text-slate-300">{query}</span> — {results.length} stocks found</p>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm border-collapse">
          <thead>
            <tr className="bg-slate-700">
              {['Company', 'Price (₹)', 'Market Cap', 'P/E', 'ROCE %', 'ROE %', 'Div Yield %', 'D/E'].map(h => (
                <th key={h} className="px-3 py-2 text-left text-slate-200 font-semibold border border-slate-600 whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {results.map((r, i) => (
              <tr key={i} className={i % 2 === 0 ? 'bg-slate-800' : 'bg-slate-800/60'}>
                <td className="px-3 py-2 border border-slate-700">
                  <div className="font-medium text-white">{r.company_name}</div>
                  {r.symbol && <div className="text-xs text-slate-500">{r.symbol}</div>}
                </td>
                <td className="px-3 py-1.5 text-slate-300 border border-slate-700">{fmtNum(r.current_price)}</td>
                <td className="px-3 py-1.5 text-slate-300 border border-slate-700 whitespace-nowrap">{fmtCr(r.market_cap)}</td>
                <td className="px-3 py-1.5 text-slate-300 border border-slate-700">{fmtNum(r.pe)}</td>
                <td className="px-3 py-1.5 text-slate-300 border border-slate-700">{fmtNum(r.roce)}</td>
                <td className="px-3 py-1.5 text-slate-300 border border-slate-700">{fmtNum(r.roe)}</td>
                <td className="px-3 py-1.5 text-slate-300 border border-slate-700">{fmtNum(r.dividend_yield)}</td>
                <td className="px-3 py-1.5 text-slate-300 border border-slate-700">{fmtNum(r.debt_to_equity)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ─── Stock Header Card ────────────────────────────────────────────────────────

function StockHeader({ result }: { result: AnalyzeResponse }) {
  const zone = result.verdict?.valuation_zone
  const zoneColor =
    zone === 'Deep Value' ? 'text-emerald-400' :
    zone === 'Fair Value' ? 'text-sky-400' :
    zone === 'Growth Priced' ? 'text-amber-400' :
    zone === 'Overvalued' ? 'text-red-400' : 'text-slate-400'

  const score = result.verdict?.probability_score?.total

  return (
    <div className="bg-slate-800 rounded-xl p-5 mb-6 border border-slate-700">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">
            {result.company_name}
            <span className="ml-2 text-slate-400 font-normal text-lg">({result.ticker})</span>
          </h1>
          <p className="text-slate-400 text-sm mt-1">{result.sector} · {result.industry}</p>
        </div>
        <div className="flex gap-6 text-right">
          <div>
            <div className="text-2xl font-bold text-white">₹{fmtNum(result.current_price)}</div>
            <div className="text-sm text-slate-400">Current Price</div>
          </div>
          <div>
            <div className="text-lg font-semibold text-white">{fmtCr(result.market_cap)}</div>
            <div className="text-sm text-slate-400">Market Cap</div>
          </div>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-4">
        <div className="bg-slate-700/50 rounded-lg px-4 py-2">
          <div className="text-xs text-slate-400">P/E</div>
          <div className="text-lg font-semibold text-white">{fmtNum(result.pe)}</div>
        </div>
        <div className="bg-slate-700/50 rounded-lg px-4 py-2">
          <div className="text-xs text-slate-400">ROCE</div>
          <div className="text-lg font-semibold text-white">{fmtNum(result.roce)}%</div>
        </div>
        <div className="bg-slate-700/50 rounded-lg px-4 py-2">
          <div className="text-xs text-slate-400">ROE</div>
          <div className="text-lg font-semibold text-white">{fmtNum(result.roe)}%</div>
        </div>
        <div className="bg-slate-700/50 rounded-lg px-4 py-2">
          <div className="text-xs text-slate-400">Book Value</div>
          <div className="text-lg font-semibold text-white">₹{fmtNum(result.book_value)}</div>
        </div>
        <div className="bg-slate-700/50 rounded-lg px-4 py-2">
          <div className="text-xs text-slate-400">EPS (TTM)</div>
          <div className="text-lg font-semibold text-white">₹{fmtNum(result.eps_ttm)}</div>
        </div>
        {zone && (
          <div className="bg-slate-700/50 rounded-lg px-4 py-2">
            <div className="text-xs text-slate-400">Valuation Zone</div>
            <div className={`text-lg font-semibold ${zoneColor}`}>{zone}</div>
          </div>
        )}
        {score != null && (
          <div className="bg-slate-700/50 rounded-lg px-4 py-2">
            <div className="text-xs text-slate-400">Outperform Score</div>
            <div className={`text-lg font-semibold ${score >= 65 ? 'text-emerald-400' : score >= 45 ? 'text-amber-400' : 'text-red-400'}`}>
              {score}/100
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Example queries ──────────────────────────────────────────────────────────

const EXAMPLES = [
  'Analyse TCS',
  'Analyse RELIANCE',
  'Analyse HDFCBANK',
  'Analyse INFY',
  'Find high ROCE low debt midcap stocks',
  'Screen for IT companies with low PE',
  'Find quality FMCG compounders',
  'Analyse BAJFINANCE',
]

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function Home() {
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadingStep, setLoadingStep] = useState(0)
  const [result, setResult] = useState<AnalyzeResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [providers, setProviders] = useState<LLMProviderInfo[]>([])
  const [selectedProvider, setSelectedProvider] = useState<string>('')
  const [selectedModel, setSelectedModel] = useState<string>('')
  const [activeTab, setActiveTab] = useState<'report' | 'data'>('report')
  const loadingInterval = useRef<NodeJS.Timeout | null>(null)
  const resultRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    getLLMProviders().then(data => {
      setProviders(data.providers)
      const def = data.providers.find(p => p.is_default)
      if (def) {
        setSelectedProvider(def.id)
        setSelectedModel(def.default_model)
      }
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (loading) {
      setLoadingStep(0)
      loadingInterval.current = setInterval(() => {
        setLoadingStep(s => (s + 1) % LOADING_STEPS.length)
      }, 3500)
    } else {
      if (loadingInterval.current) clearInterval(loadingInterval.current)
    }
    return () => { if (loadingInterval.current) clearInterval(loadingInterval.current) }
  }, [loading])

  const handleSubmit = async (q?: string) => {
    const finalQuery = q || query
    if (!finalQuery.trim()) return

    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const res = await analyze(
        finalQuery,
        selectedProvider || undefined,
        selectedModel || undefined,
      )
      setResult(res)
      setActiveTab('report')
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)
    } catch (err: any) {
      setError(err.message || 'Analysis failed')
    } finally {
      setLoading(false)
    }
  }

  const currentProviderModels =
    providers.find(p => p.id === selectedProvider)?.models || []

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100">
      {/* Navbar */}
      <nav className="sticky top-0 z-50 bg-slate-900/95 backdrop-blur border-b border-slate-800">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-emerald-500 rounded-lg flex items-center justify-center text-slate-900 font-bold text-sm">₹</div>
            <div>
              <div className="font-bold text-white leading-tight">Screener Agent</div>
              <div className="text-xs text-slate-400">Indian Equity Research</div>
            </div>
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse inline-block" />
            {selectedProvider && <span>{selectedProvider} · {selectedModel}</span>}
          </div>
        </div>
      </nav>

      <main className="max-w-6xl mx-auto px-4 py-8">
        {/* Hero */}
        {!result && !loading && (
          <div className="text-center mb-10">
            <h1 className="text-4xl font-bold text-white mb-3">
              Investment Research Agent
            </h1>
            <p className="text-slate-400 text-lg max-w-2xl mx-auto">
              Autonomous AI agent for Indian stocks. Logs into Screener.in, extracts all financial data,
              and generates a complete multi-method valuation report.
            </p>
          </div>
        )}

        {/* Query Box */}
        <div className="bg-slate-800 rounded-2xl p-6 border border-slate-700 mb-6">
          <div className="flex gap-3 mb-4">
            <input
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && !loading && handleSubmit()}
              placeholder="e.g. Analyse TCS  |  Find high ROCE low debt midcap stocks"
              className="flex-1 bg-slate-900 border border-slate-600 rounded-xl px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition"
              disabled={loading}
            />
            <button
              onClick={() => handleSubmit()}
              disabled={loading || !query.trim()}
              className="px-6 py-3 bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-700 disabled:text-slate-500 text-white font-semibold rounded-xl transition whitespace-nowrap"
            >
              {loading ? 'Analysing...' : 'Analyse →'}
            </button>
          </div>

          {/* LLM Selector */}
          <div className="flex flex-wrap gap-3 items-center">
            <span className="text-xs text-slate-500">LLM:</span>
            <select
              value={selectedProvider}
              onChange={e => {
                setSelectedProvider(e.target.value)
                const p = providers.find(p => p.id === e.target.value)
                setSelectedModel(p?.default_model || '')
              }}
              className="bg-slate-700 border border-slate-600 rounded-lg px-2 py-1 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
            >
              {providers.map(p => (
                <option key={p.id} value={p.id} disabled={!p.configured}>
                  {p.display_name}{!p.configured ? ' (no key)' : ''}
                </option>
              ))}
            </select>
            <select
              value={selectedModel}
              onChange={e => setSelectedModel(e.target.value)}
              className="bg-slate-700 border border-slate-600 rounded-lg px-2 py-1 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
            >
              {currentProviderModels.map(m => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </div>

          {/* Examples */}
          {!result && (
            <div className="mt-4 flex flex-wrap gap-2">
              {EXAMPLES.map(ex => (
                <button
                  key={ex}
                  onClick={() => { setQuery(ex); handleSubmit(ex) }}
                  disabled={loading}
                  className="px-3 py-1.5 text-xs bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg transition border border-slate-600 hover:border-slate-500"
                >
                  {ex}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Loading State */}
        {loading && (
          <div className="bg-slate-800 rounded-2xl p-10 border border-slate-700 text-center">
            <div className="flex justify-center mb-6">
              <div className="w-16 h-16 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin" />
            </div>
            <div className="text-emerald-400 font-medium text-lg mb-2 transition-all duration-500">
              {LOADING_STEPS[loadingStep]}
            </div>
            <div className="text-slate-500 text-sm">
              Full analysis takes 30–90 seconds (scraping + 4 LLM calls)
            </div>
            <div className="mt-6 flex justify-center gap-1">
              {LOADING_STEPS.map((_, i) => (
                <div
                  key={i}
                  className={`w-2 h-2 rounded-full transition-all duration-300 ${i === loadingStep ? 'bg-emerald-500 scale-125' : i < loadingStep ? 'bg-emerald-800' : 'bg-slate-700'}`}
                />
              ))}
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="bg-red-900/30 border border-red-700 rounded-2xl p-6 text-red-300">
            <div className="font-semibold mb-1">Analysis Failed</div>
            <div className="text-sm">{error}</div>
          </div>
        )}

        {/* Results */}
        {result && !loading && (
          <div ref={resultRef}>
            {result.mode === 'screening' ? (
              <div className="bg-slate-800 rounded-2xl p-6 border border-slate-700">
                <ScreeningTable
                  results={result.results || []}
                  query={result.screener_query_used || result.query || ''}
                />
              </div>
            ) : (
              <div>
                {/* Stock header card */}
                <StockHeader result={result} />

                {/* Tabs */}
                <div className="flex gap-2 mb-4 border-b border-slate-700 pb-0">
                  <button
                    onClick={() => setActiveTab('report')}
                    className={`px-4 py-2 text-sm font-medium rounded-t-lg transition ${activeTab === 'report' ? 'bg-slate-800 text-emerald-400 border border-b-0 border-slate-700' : 'text-slate-400 hover:text-slate-200'}`}
                  >
                    Full Report
                  </button>
                  <button
                    onClick={() => setActiveTab('data')}
                    className={`px-4 py-2 text-sm font-medium rounded-t-lg transition ${activeTab === 'data' ? 'bg-slate-800 text-emerald-400 border border-b-0 border-slate-700' : 'text-slate-400 hover:text-slate-200'}`}
                  >
                    Structured Data
                  </button>
                </div>

                {activeTab === 'report' && result.report_markdown && (
                  <div className="bg-slate-800 rounded-2xl rounded-tl-none p-6 border border-slate-700">
                    <div className="flex justify-between items-center mb-4">
                      <div className="text-xs text-slate-500">
                        Generated in {result.execution_time_seconds?.toFixed(1)}s · {result.llm_provider}/{result.llm_model}
                      </div>
                      <button
                        onClick={() => {
                          const blob = new Blob([result.report_markdown || ''], { type: 'text/markdown' })
                          const url = URL.createObjectURL(blob)
                          const a = document.createElement('a')
                          a.href = url
                          a.download = `${result.ticker}_report.md`
                          a.click()
                        }}
                        className="px-3 py-1 text-xs bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg border border-slate-600 transition"
                      >
                        Download .md
                      </button>
                    </div>
                    <MarkdownReport markdown={result.report_markdown} />
                  </div>
                )}

                {activeTab === 'data' && (
                  <div className="bg-slate-800 rounded-2xl rounded-tl-none p-6 border border-slate-700 space-y-6">
                    {/* Valuation Table */}
                    {result.valuation_table && result.valuation_table.length > 0 && (
                      <div>
                        <h3 className="font-semibold text-white mb-3">Valuation Table</h3>
                        <div className="overflow-x-auto">
                          <table className="min-w-full text-sm border-collapse">
                            <thead>
                              <tr className="bg-slate-700">
                                {['Method', 'Assumption', 'Value/Share (₹)', 'vs Market', 'MoS %'].map(h => (
                                  <th key={h} className="px-3 py-2 text-left text-slate-200 font-semibold border border-slate-600 whitespace-nowrap">{h}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {result.valuation_table.map((row, i) => {
                                const mos = row.mos_pct
                                const mosColor = mos == null ? '' : mos > 20 ? 'text-emerald-400' : mos > 0 ? 'text-sky-400' : 'text-red-400'
                                return (
                                  <tr key={i} className={i % 2 === 0 ? 'bg-slate-800' : 'bg-slate-800/60'}>
                                    <td className="px-3 py-1.5 border border-slate-700 font-medium text-slate-200">{row.method}</td>
                                    <td className="px-3 py-1.5 border border-slate-700 text-slate-400 text-xs">{row.assumption}</td>
                                    <td className="px-3 py-1.5 border border-slate-700 text-white font-medium">
                                      {row.value_per_share ? `₹${row.value_per_share.toLocaleString('en-IN')}` : '—'}
                                    </td>
                                    <td className="px-3 py-1.5 border border-slate-700 text-slate-400 text-xs">{row.vs_market || '—'}</td>
                                    <td className={`px-3 py-1.5 border border-slate-700 font-medium ${mosColor}`}>
                                      {mos != null ? `${mos.toFixed(1)}%` : '—'}
                                    </td>
                                  </tr>
                                )
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}

                    {/* Buy Ranges */}
                    {result.verdict?.buy_ranges && (
                      <div>
                        <h3 className="font-semibold text-white mb-3">Buy/Sell Ranges</h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                          {result.verdict.buy_ranges.map((br, i) => {
                            const color =
                              br.action.includes('Strong Buy') ? 'border-emerald-500 bg-emerald-900/20' :
                              br.action.includes('Buy') ? 'border-sky-500 bg-sky-900/20' :
                              br.action.includes('Accumulate') ? 'border-blue-500 bg-blue-900/20' :
                              br.action.includes('Hold') ? 'border-slate-500 bg-slate-700/20' :
                              'border-red-500 bg-red-900/20'
                            const priceStr = br.price_from == null
                              ? `Below ₹${br.price_to?.toLocaleString('en-IN')}`
                              : br.price_to == null
                              ? `Above ₹${br.price_from?.toLocaleString('en-IN')}`
                              : `₹${br.price_from?.toLocaleString('en-IN')} – ₹${br.price_to?.toLocaleString('en-IN')}`
                            return (
                              <div key={i} className={`rounded-xl p-4 border ${color}`}>
                                <div className="font-bold text-white">{br.action}</div>
                                <div className="text-lg font-semibold text-slate-200 mt-1">{priceStr}</div>
                                <div className="text-xs text-slate-400 mt-1">{br.rationale}</div>
                              </div>
                            )
                          })}
                        </div>
                      </div>
                    )}

                    {/* Key Monitorables */}
                    {result.verdict?.key_monitorables && result.verdict.key_monitorables.length > 0 && (
                      <div>
                        <h3 className="font-semibold text-white mb-3">Key Monitorables (Watch Each Quarter)</h3>
                        <div className="space-y-2">
                          {result.verdict.key_monitorables.map((m, i) => (
                            <div key={i} className="bg-slate-700/30 rounded-lg px-4 py-3 flex items-start gap-4">
                              <div className="font-medium text-emerald-400 min-w-32">{m.metric}</div>
                              <div className="text-slate-300 flex-1">{m.what_to_watch}</div>
                              <div className="text-xs text-slate-500 whitespace-nowrap">{m.threshold}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* New query button */}
            <div className="mt-6 text-center">
              <button
                onClick={() => { setResult(null); setQuery('') }}
                className="px-6 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-xl border border-slate-600 transition text-sm"
              >
                ← New Query
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
