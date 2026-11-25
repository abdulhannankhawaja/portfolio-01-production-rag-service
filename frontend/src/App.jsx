import { useEffect, useRef, useState } from 'react'
import './App.css'

async function api(path, options = {}) {
  const headers = new Headers(options.headers)
  const token = sessionStorage.getItem('access_token')
  if (token && !path.startsWith('/auth/')) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  const response = await fetch(path, { ...options, headers })
  if (response.status === 401 && token) {
    sessionStorage.removeItem('access_token')
    sessionStorage.removeItem('username')
    window.dispatchEvent(new Event('auth-expired'))
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `Request failed (${response.status})`)
  }
  return response.status === 204 ? null : response.json()
}

function AuthScreen({ onAuthenticated }) {
  const [mode, setMode] = useState('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [message, setMessage] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function submit(event) {
    event.preventDefault()
    setSubmitting(true)
    setMessage('')
    try {
      if (mode === 'signup') {
        await api('/auth/signup', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password }),
        })
      }
      const result = await api('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      sessionStorage.setItem('access_token', result.access_token)
      sessionStorage.setItem('username', result.username)
      onAuthenticated(result.access_token, result.username)
    } catch (error) {
      setMessage(error.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <div className="brand-mark auth-mark" aria-hidden="true">R</div>
        <p className="eyebrow">Private knowledge workspace</p>
        <h1>{mode === 'login' ? 'Welcome back' : 'Create your account'}</h1>
        <p className="auth-description">Sign in to access your own documents and grounded answers.</p>
        <label htmlFor="auth-username">Username</label>
        <input
          id="auth-username"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          autoComplete="username"
          minLength={3}
          maxLength={64}
          required
        />
        <label htmlFor="auth-password">Password</label>
        <input
          id="auth-password"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
          minLength={mode === 'signup' ? 12 : 1}
          maxLength={128}
          required
        />
        {mode === 'signup' && <small className="password-hint">Use at least 12 characters.</small>}
        {message && <p className="auth-error" role="alert">{message}</p>}
        <button type="submit" disabled={submitting}>{submitting ? 'Please wait...' : mode === 'login' ? 'Sign in' : 'Create account'}</button>
        <p className="auth-switch">
          {mode === 'login' ? 'New here?' : 'Already have an account?'}{' '}
          <button type="button" onClick={() => { setMode(mode === 'login' ? 'signup' : 'login'); setMessage('') }}>
            {mode === 'login' ? 'Create account' : 'Sign in'}
          </button>
        </p>
      </form>
    </main>
  )
}

function formatLocation(item) {
  if (item.page != null) {
    return item.filename?.toLowerCase().endsWith('.pptx')
      ? `Slide ${item.page}`
      : `Page ${item.page}`
  }
  return item.section || 'Location unavailable'
}

function formatFileType(filename) {
  return filename.split('.').pop()?.toUpperCase() || 'FILE'
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function ObservabilityDashboard({ onClose }) {
  const [report, setReport] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  async function refresh() {
    setLoading(true)
    setError('')
    try {
      setReport(await api('/observability'))
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let active = true
    api('/observability')
      .then((data) => {
        if (active) setReport(data)
      })
      .catch((requestError) => {
        if (active) setError(requestError.message)
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => { active = false }
  }, [])

  const metric = (value) => value == null ? '—' : `${value} ms`
  const costPerQuestion = report?.cost.known_average_per_question_usd

  return (
    <div className="observability-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose()
    }}>
      <section className="observability-dashboard" role="dialog" aria-modal="true" aria-labelledby="observability-title">
        <header className="dashboard-header">
          <div>
            <p className="eyebrow">Service monitoring</p>
            <h2 id="observability-title">Observability</h2>
          </div>
          <div className="dashboard-actions">
            <button type="button" onClick={refresh} disabled={loading}>{loading ? 'Refreshing...' : 'Refresh'}</button>
            <button type="button" className="dashboard-close" onClick={onClose} aria-label="Close observability dashboard">×</button>
          </div>
        </header>
        {error && <p className="notice" role="alert">{error}</p>}
        {!report && loading && <p className="empty-state">Loading metrics...</p>}
        {report && (
          <>
            <div className="metric-grid">
              <article className="metric-card"><span>Request latency · p50</span><strong>{metric(report.latency_ms.p50)}</strong></article>
              <article className="metric-card"><span>Request latency · p95</span><strong>{metric(report.latency_ms.p95)}</strong></article>
              <article className="metric-card"><span>Request error rate</span><strong>{(report.error_rate * 100).toFixed(1)}%</strong></article>
              <article className="metric-card"><span>Question error rate</span><strong>{(report.question_error_rate * 100).toFixed(1)}%</strong></article>
              <article className="metric-card"><span>Requests tracked</span><strong>{report.request_count}</strong></article>
              <article className="metric-card"><span>Question tokens · in / out</span><strong>{report.tokens.input} / {report.tokens.output}</strong><small>{report.tokens.estimated_questions} question(s) use estimated counts</small></article>
              <article className="metric-card"><span>Provider cost / question</span><strong>{costPerQuestion == null ? 'Not configured' : `$${costPerQuestion.toFixed(6)}`}</strong><small>{report.cost.questions_with_known_cost} question(s) with known cost</small></article>
            </div>
            <div className="trace-section">
              <h3>Recent request traces</h3>
              {report.traces.length === 0 ? <p className="empty-state">No requests recorded yet.</p> : (
                <div className="trace-list">
                  {report.traces.map((trace) => (
                    <details className="trace-item" key={trace.trace_id}>
                      <summary>
                        <span className="trace-status">{trace.status_code}</span>
                        <strong>{trace.method} {trace.path}</strong>
                        <span>{trace.duration_ms.toFixed(1)} ms</span>
                        <code>{trace.trace_id.slice(0, 8)}</code>
                      </summary>
                      <div className="trace-summary">
                        <span>{trace.model || 'No model call'}</span>
                        <span>Tokens: {trace.input_tokens ?? '—'} in / {trace.output_tokens ?? '—'} out ({trace.token_source})</span>
                        <span>Cost: {trace.cost_usd == null ? 'unknown' : `$${trace.cost_usd.toFixed(6)}`}</span>
                        <span>Retrieved: {trace.retrieved_chunks}</span>
                      </div>
                      <ol className="span-list">
                        {trace.spans.map((span) => (
                          <li key={span.span_id} className={`span-row span-${span.status}`}>
                            <strong>{span.name}</strong>
                            <span>{span.duration_ms.toFixed(2)} ms · {span.status}</span>
                            {span.attributes.reason && <small>{span.attributes.reason}</small>}
                          </li>
                        ))}
                      </ol>
                    </details>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
        <p className="dashboard-footnote">Local telemetry stores spans and metrics only, not prompts or document text. Gemini answer costs are estimated from configured rates; local generation has no provider charge. Embedding-provider cost is not included.</p>
      </section>
    </div>
  )
}

function App() {
  const [authToken, setAuthToken] = useState(() => sessionStorage.getItem('access_token'))
  const [username, setUsername] = useState(() => sessionStorage.getItem('username') || '')
  const [documents, setDocuments] = useState([])
  const [file, setFile] = useState(null)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState(null)
  const [citations, setCitations] = useState([])
  const [chunks, setChunks] = useState([])
  const [notice, setNotice] = useState('')
  const [loadingDocuments, setLoadingDocuments] = useState(
    () => Boolean(sessionStorage.getItem('access_token')),
  )
  const [uploading, setUploading] = useState(false)
  const [asking, setAsking] = useState(false)
  const [observabilityOpen, setObservabilityOpen] = useState(false)
  const fileInput = useRef(null)

  async function loadDocuments() {
    setLoadingDocuments(true)
    try {
      setDocuments(await api('/documents'))
    } catch (error) {
      setNotice(error.message)
    } finally {
      setLoadingDocuments(false)
    }
  }

  useEffect(() => {
    if (!authToken) return
    api('/documents')
      .then(setDocuments)
      .catch((error) => setNotice(error.message))
      .finally(() => setLoadingDocuments(false))
  }, [authToken])

  useEffect(() => {
    function expireSession() {
      setAuthToken(null)
      setUsername('')
      setDocuments([])
      setNotice('Your session expired. Please sign in again.')
    }
    window.addEventListener('auth-expired', expireSession)
    return () => window.removeEventListener('auth-expired', expireSession)
  }, [])

  useEffect(() => {
    if (!window.matchMedia('(hover: hover) and (pointer: fine)').matches) return

    const root = document.documentElement
    let frameId = 0

    function moveGlow(event) {
      cancelAnimationFrame(frameId)
      frameId = requestAnimationFrame(() => {
        root.style.setProperty('--cursor-x', `${event.clientX}px`)
        root.style.setProperty('--cursor-y', `${event.clientY}px`)
        root.classList.add('cursor-glow-active')
      })
    }

    function hideGlow() {
      root.classList.remove('cursor-glow-active')
    }

    window.addEventListener('pointermove', moveGlow, { passive: true })
    window.addEventListener('blur', hideGlow)
    return () => {
      cancelAnimationFrame(frameId)
      window.removeEventListener('pointermove', moveGlow)
      window.removeEventListener('blur', hideGlow)
      root.classList.remove('cursor-glow-active')
      root.style.removeProperty('--cursor-x')
      root.style.removeProperty('--cursor-y')
    }
  }, [])

  async function uploadDocument(event) {
    event.preventDefault()
    if (!file) return
    setUploading(true)
    setNotice('')
    const form = new FormData()
    form.append('file', file)
    try {
      await api('/documents', { method: 'POST', body: form })
      setFile(null)
      if (fileInput.current) fileInput.current.value = ''
      setNotice(`${file.name} uploaded successfully`)
      await loadDocuments()
    } catch (error) {
      setNotice(error.message)
    } finally {
      setUploading(false)
    }
  }

  async function deleteDocument(document) {
    setNotice('')
    try {
      await api(`/documents/${document.id}`, { method: 'DELETE' })
      setNotice(`${document.filename} deleted`)
      await loadDocuments()
    } catch (error) {
      setNotice(error.message)
    }
  }

  async function askQuestion(event) {
    event.preventDefault()
    const trimmed = question.trim()
    if (!trimmed) return
    setAsking(true)
    setAnswer(null)
    setCitations([])
    setChunks([])
    setNotice('')
    try {
      const result = await api('/questions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: trimmed, top_k: 5 }),
      })
      setAnswer(result)
      setCitations(result.citations)
      setChunks(result.retrieved_chunks)
    } catch (error) {
      setNotice(error.message)
    } finally {
      setAsking(false)
    }
  }

  function logout() {
    sessionStorage.removeItem('access_token')
    sessionStorage.removeItem('username')
    setAuthToken(null)
    setUsername('')
    setDocuments([])
    setAnswer(null)
    setNotice('')
  }

  if (!authToken) {
    return (
      <div className="app-shell auth-app-shell">
        <AuthScreen onAuthenticated={(token, authenticatedUsername) => {
          setAuthToken(token)
          setUsername(authenticatedUsername)
          setLoadingDocuments(true)
        }} />
      </div>
    )
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">R</div>
          <div><strong>NIST RAG</strong><span>Production knowledge workspace</span></div>
        </div>
        <div className="topbar-actions">
          <button className="observability-button" type="button" onClick={() => setObservabilityOpen(true)}>Observability</button>
          <span className="user-label">{username}</span>
          <button className="logout-button" type="button" onClick={logout}>Sign out</button>
          <div className="status"><span /> Local service</div>
        </div>
      </header>
      <main className="workspace">
        <aside className="sidebar">
          <div className="section-heading">
            <div><p className="eyebrow">Knowledge base</p><h2>Documents</h2></div>
            <span className="count">{documents.length}</span>
          </div>
          <form className="upload-card" onSubmit={uploadDocument}>
            <input
              ref={fileInput}
              id="file"
              type="file"
              accept=".pdf,.docx,.txt,.md,.pptx"
              onChange={(event) => setFile(event.target.files?.[0] || null)}
            />
            <label htmlFor="file" className={file ? 'file-selected' : ''}>
              <span className="upload-icon" aria-hidden="true">+</span>
              <span><strong>{file ? file.name : 'Upload document'}</strong><small>{file ? formatBytes(file.size) : 'PDF, DOCX, TXT, MD or PPTX'}</small></span>
            </label>
            <button type="submit" disabled={!file || uploading}>{uploading ? 'Indexing...' : 'Index document'}</button>
          </form>
          <div className="document-list" aria-live="polite">
            {loadingDocuments && <p className="empty-state">Loading documents...</p>}
            {!loadingDocuments && documents.length === 0 && <p className="empty-state">No documents indexed yet.</p>}
            {documents.map((document) => (
              <article className="document-row" key={document.id}>
                <div className="file-icon">{formatFileType(document.filename)}</div>
                <div className="document-meta">
                  <strong title={document.filename}>{document.filename}</strong>
                  <span>{document.chunk_count} chunks · {formatBytes(document.size_bytes)}</span>
                </div>
                <button className="icon-button" type="button" title={`Delete ${document.filename}`} aria-label={`Delete ${document.filename}`} onClick={() => deleteDocument(document)}>×</button>
              </article>
            ))}
          </div>
        </aside>
        <section className="chat-panel">
          <div className="chat-heading"><p className="eyebrow">Ask the corpus</p><h1>NIST Production RAG</h1></div>
          <div className="chat-scroll">
            {!answer && !asking && (
              <div className="welcome">
                <div className="welcome-icon" aria-hidden="true">?</div>
                <h2>What would you like to know?</h2>
                <p>Ask a grounded question about the documents in your knowledge base.</p>
              </div>
            )}
            {asking && (
              <div className="answer-card loading-card"><span className="spinner" /><div><strong>Searching and generating</strong><p>Retrieving relevant passages...</p></div></div>
            )}
            {answer && (
              <div className="answer-card">
                <div className="answer-label">
                  <span>Answer</span>
                  <span className={answer.grounded ? 'badge grounded' : 'badge'}>{answer.refusal ? 'Refused' : answer.grounded ? 'Grounded' : 'Unverified'}</span>
                </div>
                <p className="answer-text">{answer.answer}</p>
                {citations.length > 0 && (
                  <div className="citations">
                    <h3>Sources</h3>
                    {citations.map((citation) => (
                      <div className="citation" key={citation.chunk_id}>
                        <span className="citation-rank">{citation.rank}</span>
                        <div><strong>{citation.filename}</strong><small>{formatLocation(citation)} · Chunk {citation.chunk_index + 1}</small></div>
                      </div>
                    ))}
                  </div>
                )}
                {chunks.length > 0 && (
                  <details className="retrieval-details">
                    <summary>{chunks.length} retrieved passages</summary>
                    <div className="chunk-list">
                      {chunks.map((chunk) => (
                        <article className="chunk" key={chunk.chunk_id}>
                          <div><strong>Rank {chunk.rank}</strong><span>{chunk.filename} · {formatLocation(chunk)} · {chunk.score.toFixed(3)}</span></div>
                          <p>{chunk.text}</p>
                        </article>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            )}
            {notice && <div className="notice" role="status">{notice}</div>}
          </div>
          <form className="question-form" onSubmit={askQuestion}>
            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ask a question about your documents..."
              maxLength={2000}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) askQuestion(event)
              }}
            />
            <button type="submit" disabled={!question.trim() || asking} aria-label="Ask question"><span>Ask</span><span aria-hidden="true">→</span></button>
          </form>
        </section>
      </main>
      {observabilityOpen && <ObservabilityDashboard onClose={() => setObservabilityOpen(false)} />}
    </div>
  )
}

export default App
