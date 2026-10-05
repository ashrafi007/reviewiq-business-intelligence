import { useState } from 'react'
import { useBusinesses } from '../context/BusinessContext'
import { postChat } from '../api'

const SUGGESTED_QUESTIONS = [
  'What are customers complaining about most?',
  'How has sentiment changed recently?',
  'Are there any fake or suspicious reviews?',
  'What do people say about the service?',
]

function renderMarkdownBold(text) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g)
  return parts.map((part, i) =>
    part.startsWith('**') && part.endsWith('**') ? (
      <strong key={i}>{part.slice(2, -2)}</strong>
    ) : (
      part
    ),
  )
}

export default function Chatbot() {
  const { selected, selectedId } = useBusinesses()
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const send = async (question) => {
    if (!question.trim() || !selectedId) return
    setInput('')
    setError(null)
    setMessages((m) => [...m, { role: 'user', text: question }])
    setLoading(true)
    try {
      const res = await postChat(question, selectedId)
      setMessages((m) => [...m, { role: 'assistant', text: res.answer, sources: res.sources }])
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  if (!selectedId) return null

  return (
    <div className="flex h-[calc(100vh-7rem)] flex-col rounded-xl bg-slate-900 shadow-sm">
      <div className="border-b border-slate-700 px-5 py-4">
        <h1 className="text-lg font-semibold text-slate-100">Ask about {selected?.name}</h1>
        <p className="text-xs text-slate-400">Answers are grounded in this restaurant's actual reviews.</p>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
        {messages.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
            <p className="text-sm text-slate-400">Try asking one of these:</p>
            <div className="flex flex-wrap justify-center gap-2">
              {SUGGESTED_QUESTIONS.map((q) => (
                <button
                  key={q}
                  onClick={() => send(q)}
                  className="rounded-full border border-slate-600 px-3 py-1.5 text-sm text-slate-200 hover:border-indigo-400 hover:text-indigo-300"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[75%] space-y-2`}>
              <div
                className={`rounded-2xl px-4 py-2.5 text-sm ${
                  m.role === 'user'
                    ? 'bg-indigo-600 text-white'
                    : 'bg-slate-800 text-slate-100'
                }`}
              >
                {m.role === 'assistant' ? renderMarkdownBold(m.text) : m.text}
              </div>
              {m.sources?.length > 0 && (
                <div className="space-y-1.5">
                  {m.sources.slice(0, 3).map((s, j) => (
                    <div key={j} className="rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-xs text-slate-300">
                      <div className="flex items-center justify-between text-slate-400">
                        <span>{s.date}</span>
                        <span>{s.rating ? `${s.rating}★` : 'rating unknown'}</span>
                      </div>
                      <p className="mt-1 line-clamp-2 text-slate-300">{s.text}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="flex items-center gap-2 rounded-2xl bg-slate-800 px-4 py-2.5 text-sm text-slate-300">
              <span className="h-2 w-2 animate-bounce rounded-full bg-indigo-400 [animation-delay:-0.2s]" />
              <span className="h-2 w-2 animate-bounce rounded-full bg-indigo-400 [animation-delay:-0.1s]" />
              <span className="h-2 w-2 animate-bounce rounded-full bg-indigo-400" />
            </div>
          </div>
        )}

        {error && (
          <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-2 text-sm text-red-300">
            {error}
          </div>
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          send(input)
        }}
        className="flex items-center gap-2 border-t border-slate-700 px-5 py-4"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question about this restaurant's reviews…"
          className="flex-1 rounded-full border border-slate-600 bg-slate-800 px-4 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-indigo-400 focus:outline-none"
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="rounded-full bg-indigo-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          Send
        </button>
      </form>
    </div>
  )
}
