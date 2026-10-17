import { useEffect, useState } from 'react'
import './App.css'

const API = '/api'
const terminal = new Set(['completed', 'failed', 'cancelled'])
const milliseconds = (value) => `${(value * 1000).toFixed(2)} ms`

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, options)
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(typeof data.detail === 'string' ? data.detail : `Request failed (${response.status})`)
  }
  return response.json()
}

function Results({ report, id }) {
  const before = report.final_comparison?.before || report.baseline.benchmarks || {}
  const after = report.outcome === 'improved' ? report.final_comparison.after : before
  const titles = { improved: 'A measured improvement', unchanged: 'Original source preserved',
    compiled: 'Build passed', benchmarked: 'Baseline measured' }
  return (
    <section className="card results" aria-labelledby="results-title">
      <div className="section-heading"><div><span className="eyebrow">RESULTS</span>
        <h2 id="results-title">{titles[report.outcome]}</h2></div>
        {report.outcome === 'improved' && <span className="gain">{(report.final_comparison.gain * 100).toFixed(1)}% faster</span>}
      </div>
      <p>{report.mode === 'compile' ? 'Compilation succeeded. The program was not executed and no model was called.' :
        report.outcome === 'improved' ? 'The final change passed output checks and a fresh comparison against the original.' :
          'No source changes are included in this download.'}</p>
      {Object.keys(before).length > 0 && <div className="table-scroll"><table>
        <thead><tr><th>Workload</th><th>Original median</th><th>Result median</th><th>Result variation (MAD)</th></tr></thead>
        <tbody>{Object.entries(before).map(([name, stats]) => <tr key={name}>
          <td>{name}</td><td>{milliseconds(stats.median_seconds)}</td>
          <td>{milliseconds(after[name].median_seconds)}</td><td>± {milliseconds(after[name].mad_seconds)}</td>
        </tr>)}</tbody>
      </table></div>}
      {report.warnings.map((warning, i) => <p className="notice" key={i}>{warning}</p>)}
      <div className="actions">
        <a className="button primary" href={`${API}/jobs/${id}/download`}>Download project & report</a>
        <a className="button secondary" href={`${API}/jobs/${id}/report`} target="_blank" rel="noreferrer">View full report</a>
      </div>
      {report.baseline.profile && <details><summary>Profiling evidence</summary>
        {report.baseline.profile.available ? <><p>Instruction counts for {report.baseline.profile.workload}; these are not elapsed times.</p>
          <pre>{report.baseline.profile.report}</pre></> : <p>{report.baseline.profile.reason}</p>}
      </details>}
      {report.attempts.length > 0 && <div className="attempts"><h3>Proposal history</h3>
        {report.attempts.map(attempt => <details key={attempt.number}>
          <summary>Attempt {attempt.number} <span className={`badge ${attempt.status}`}>{attempt.status.replace('_', ' ')}</span></summary>
          <p>{attempt.explanation}</p><p>{attempt.reason}</p>
          {attempt.diff && <pre>{attempt.diff}</pre>}
        </details>)}
      </div>}
      {report.diff && <details open><summary>Final source changes</summary><pre>{report.diff}</pre></details>}
    </section>
  )
}

export default function App() {
  const [health, setHealth] = useState(null)
  const [file, setFile] = useState(null)
  const [mode, setMode] = useState('optimize')
  const [configuration, setConfiguration] = useState('')
  const [trusted, setTrusted] = useState(false)
  const [jobId, setJobId] = useState(() => localStorage.getItem('optimizer-job') || '')
  const [job, setJob] = useState(null)
  const [report, setReport] = useState(null)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [retry, setRetry] = useState(0)
  const busy = submitting || Boolean(jobId && (!job || !terminal.has(job.status)))

  useEffect(() => {
    const controller = new AbortController()
    request('/health', { signal: controller.signal }).then(setHealth).catch(err => {
      if (err.name !== 'AbortError') setError('Cannot reach the backend. Start the API on localhost:8000.')
    })
    return () => controller.abort()
  }, [retry])

  useEffect(() => {
    if (!jobId) return
    const controller = new AbortController()
    let timer
    async function poll() {
      try {
        const next = await request(`/jobs/${jobId}`, { signal: controller.signal })
        setJob(next)
        if (next.status === 'completed') {
          const result = await request(`/jobs/${jobId}/report`, { signal: controller.signal })
          setReport(result)
        } else if (!terminal.has(next.status)) timer = setTimeout(poll, 1200)
      } catch (err) {
        if (err.name !== 'AbortError') setError(err.message)
      }
    }
    poll()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [jobId, retry])

  function choose(selected) {
    if (busy) return
    if (!selected || !/\.(zip|cpp|cc|cxx|c)$/i.test(selected.name)) {
      setError('Choose a C/C++ source file or a ZIP project.')
      setFile(null)
      return
    }
    if (selected.size > 20 * 1024 * 1024) {
      setError('The upload limit is 20 MiB.')
      return
    }
    setFile(selected)
    setError('')
  }

  async function submit(event) {
    event.preventDefault()
    if (!file || busy) return
    setError('')
    setSubmitting(true)
    try {
      const custom = configuration.trim() ? JSON.parse(configuration) : {}
      if (!custom || Array.isArray(custom) || typeof custom !== 'object') throw new Error('Configuration must be a JSON object.')
      const body = new FormData()
      body.append('project', file)
      body.append('options', JSON.stringify({ ...custom, mode }))
      const next = await request('/jobs', { method: 'POST', body })
      setReport(null)
      setJob(next)
      setJobId(next.id)
      localStorage.setItem('optimizer-job', next.id)
    } catch (err) { setError(err.message) }
    finally { setSubmitting(false) }
  }

  async function cancel() {
    try { setJob(await request(`/jobs/${jobId}`, { method: 'DELETE' })) }
    catch (err) { setError(err.message) }
  }

  function clearJob() {
    localStorage.removeItem('optimizer-job')
    setJobId(''); setJob(null); setReport(null); setError('')
  }

  return (
    <main>
      <header className="masthead"><a className="brand" href="/">C<span>++</span> / OPTIMIZER</a>
        <span className="local-badge">Local first · Free-tier compatible</span></header>
      <section className="hero"><span className="eyebrow">MEASURE. VERIFY. IMPROVE.</span>
        <h1>Faster code.<br /><span>Evidence included.</span></h1>
        <p>Find focused C++ improvements, check the results, and measure the difference. Your project structure stays intact.</p>
      </section>
      <div className="workspace">
        <form className="card" onSubmit={submit}>
          <div className="section-heading"><h2>Start a run</h2><span className="step">01 / INPUT</span></div>
          <fieldset disabled={busy}>
            <label className="drop-zone" onDragOver={event => event.preventDefault()}
              onDrop={event => { event.preventDefault(); choose(event.dataTransfer.files[0]) }}>
              <span className="upload-icon" aria-hidden="true">↑</span>
              <strong>{file ? file.name : 'Drop your project here'}</strong>
              <span>C/C++ file or ZIP · up to 20 MiB</span>
              <input type="file" aria-label="Project upload" accept=".zip,.cpp,.cc,.cxx,.c"
                onChange={event => choose(event.target.files[0])} />
            </label>
            <label htmlFor="mode">What would you like to do?</label>
            <select id="mode" value={mode} onChange={event => setMode(event.target.value)}>
              <option value="optimize">Optimize and verify</option>
              <option value="benchmark">Benchmark only — no model needed</option>
              <option value="compile">Compile only — do not execute</option>
            </select>
            <details className="configuration"><summary>Workloads & build configuration</summary>
              <p>Include an optimizer.json in your ZIP, or enter overrides below. Supply deterministic inputs and outputs; printed timings or random results will fail validation.</p>
              <label htmlFor="configuration">JSON options</label>
              <textarea id="configuration" rows={10} spellCheck="false" value={configuration}
                placeholder={'{\n  "cases": [\n    {"name": "small", "args": ["1000"], "stdin": ""},\n    {"name": "large", "args": ["100000"]}\n  ],\n  "attempts": 3,\n  "repeats": 7\n}'}
                onChange={event => setConfiguration(event.target.value)} />
              <p className="hint">Without overrides: all source files, C++17, no arguments, seven measurements. CMake projects also need build, cmake_target, and executable.</p>
            </details>
            {health?.runner === 'native' && <label className="checkbox"><input type="checkbox" checked={trusted}
              onChange={event => setTrusted(event.target.checked)} />I trust this project to run on my machine. Native mode is not isolated.</label>}
            {mode === 'optimize' && <p className="hint">Optimization sends selected source code to Groq using your configured API key. Benchmark and compile modes make no model calls.</p>}
            <button className="primary" disabled={!file || !health || !health.runner_available ||
              (health.runner === 'native' && !trusted) || (mode === 'optimize' && !health.model_configured)}>
              {submitting ? 'Uploading…' : mode === 'compile' ? 'Check build' : mode === 'benchmark' ? 'Measure baseline' : 'Find improvements'} <span aria-hidden="true">↗</span>
            </button>
          </fieldset>
        </form>
        <aside>
          <section className="card compact"><span className="eyebrow">HOW IT WORKS</span><ol className="steps">
            <li><strong>Understand the workload</strong><span>Build, index source, and collect profiling evidence.</span></li>
            <li><strong>Make a focused proposal</strong><span>A bounded model loop suggests source edits.</span></li>
            <li><strong>Check every change</strong><span>Compare outputs, repeat measurements, and keep only validated gains.</span></li>
          </ol></section>
          <section className="card compact"><span className="eyebrow">ENVIRONMENT</span>
            <p><span className={`dot ${health ? 'ready' : ''}`} />{health ? `${health.runner === 'docker' ? 'Isolated Docker' : 'Trusted native'} runner` : 'Connecting to backend…'}</p>
            {health && !health.runner_available && <p className="notice">Runner not found. Follow the README setup instructions.</p>}
            {health && !health.model_configured && <p className="notice">Groq key not configured. You can still compile and benchmark.</p>}
            <p className="hint">Results stay on this machine. Jobs run one at a time to reduce benchmark interference.</p>
          </section>
        </aside>
      </div>
      {error && <div className="card error" role="alert"><p>{error}</p><div className="actions">
        <button className="secondary" onClick={() => { setError(''); setRetry(retry + 1) }}>Retry connection</button>
        {jobId && <button className="secondary" onClick={clearJob}>Dismiss saved job</button>}
      </div></div>}
      {job && <section className="card progress-card" aria-live="polite">
        <div className="section-heading"><div><span className="eyebrow">{job.status.toUpperCase()}</span><h2>{job.stage}</h2></div>
          {!terminal.has(job.status) && <button type="button" className="secondary" onClick={cancel} disabled={job.status === 'cancelling'}>Cancel run</button>}
        </div>
        {!terminal.has(job.status) && <progress max="100" value={job.progress} aria-label="Optimization progress" />}
        {job.error && <pre className="error">{job.error}</pre>}
      </section>}
      {report && <Results report={report} id={jobId} />}
      <footer>Performance depends on your workloads and machine. Passing supplied tests does not prove equivalence for every input.</footer>
    </main>
  )
}
