import { useEffect, useState } from 'react'
import { Activity, ArrowRight, Check, CircleAlert, Database, RefreshCw, ShieldCheck, Sparkles, X } from 'lucide-react'

type Batch = { id:string; name:string; status:string }
type Summary = { batch:Batch; total_records:number; matched_records:number; exceptions:number; open_exceptions:number; resolved_exceptions:number; match_rate:number; resolution_rate:number; accuracy:number|null }
type Evidence = { payment_id:string; payment_amount:string; settlement_amount:string|null; bank_amount:string|null }
type ExceptionItem = { id:string; exception_type:string; severity:string; ai_reason:string; ai_confidence:string; evidence:Evidence; status:string; created_at:string }

async function json<T>(path:string, init?:RequestInit):Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) throw new Error(await response.text())
  return response.json()
}

export function App() {
  const [batches,setBatches] = useState<Batch[]>([])
  const [active,setActive] = useState('')
  const [summary,setSummary] = useState<Summary|null>(null)
  const [exceptions,setExceptions] = useState<ExceptionItem[]>([])
  const [busy,setBusy] = useState(false)
  const [error,setError] = useState('')

  async function load(batchId?:string) {
    const all = await json<Batch[]>('/api/v1/batches')
    setBatches(all)
    const id = batchId || active || all[0]?.id
    if (!id) return
    setActive(id)
    const [nextSummary,nextExceptions] = await Promise.all([
      json<Summary>(`/api/v1/batches/${id}/summary`), json<ExceptionItem[]>(`/api/v1/batches/${id}/exceptions`)
    ])
    setSummary(nextSummary); setExceptions(nextExceptions)
  }

  useEffect(() => { load().catch(e => setError(e.message)) }, [])

  async function generate() {
    setBusy(true); setError('')
    try {
      const batch = await json<Batch>('/api/v1/demo/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({records:160,anomaly_rate:.18,seed:Date.now()})})
      await load(batch.id)
    } catch(e) { setError(e instanceof Error ? e.message : 'Generation failed') } finally { setBusy(false) }
  }

  async function review(id:string,decision:'APPROVE'|'REJECT') {
    await json(`/api/v1/exceptions/${id}/review`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({decision,comment:`${decision === 'APPROVE' ? 'Evidence accepted' : 'Mismatch confirmed'} by finance reviewer`})})
    await load(active)
  }

  const open = exceptions.filter(item => item.status === 'PENDING_REVIEW')
  return <main>
    <header>
      <a className="brand" href="#"><span className="brand-mark">FC</span><span>FINANCE<br/>CONTROL</span></a>
      <div className="system"><span></span> SYSTEM OPERATIONAL</div>
      <button className="generate" onClick={generate} disabled={busy}><Sparkles size={16}/>{busy?'RECONCILING…':'GENERATE DEMO BATCH'}</button>
    </header>

    <section className="hero">
      <div><p className="eyebrow">AUTONOMOUS RECONCILIATION / CONTROL ROOM</p><h1>Every rupee.<br/><em>Accounted for.</em></h1></div>
      <div className="hero-copy">Deterministic matching first. Structured AI reasoning only where evidence is ambiguous. Human control always remains final.</div>
    </section>

    {error && <div className="error">API unavailable: {error}</div>}
    {!summary ? <section className="empty"><Database size={42}/><h2>No reconciliation runs yet</h2><p>Generate a labeled synthetic batch to exercise the full control loop.</p><button onClick={generate}>Create first batch <ArrowRight size={16}/></button></section> : <>
      <section className="runbar">
        <div><span>ACTIVE RUN</span><select value={active} onChange={e=>load(e.target.value)}>{batches.map(batch=><option value={batch.id} key={batch.id}>{batch.name}</option>)}</select></div>
        <div><span>RUN ID</span><strong>{summary.batch.id}</strong></div>
        <div><span>STATE</span><strong className="positive"><Check size={14}/> {summary.batch.status}</strong></div>
        <button className="icon-button" onClick={()=>load(active)} aria-label="Refresh"><RefreshCw size={17}/></button>
      </section>

      <section className="metrics">
        <Metric label="RECORDS CONTROLLED" value={summary.total_records.toLocaleString()} note="PAYMENT EVENTS" icon={<Database/>}/>
        <Metric label="DETERMINISTIC MATCH" value={`${summary.match_rate}%`} note={`${summary.matched_records} CLEARED`} icon={<ShieldCheck/>}/>
        <Metric label="OPEN EXCEPTIONS" value={String(summary.open_exceptions).padStart(2,'0')} note={`${summary.resolved_exceptions} RESOLVED`} alert icon={<CircleAlert/>}/>
        <Metric label="BENCHMARK ACCURACY" value={summary.accuracy == null ? 'N/A' : `${summary.accuracy}%`} note={`${summary.resolution_rate}% CONTROLLED`} icon={<Activity/>}/>
      </section>

      <section className="workspace">
        <div className="queue">
          <div className="section-head"><div><p className="eyebrow">HUMAN-IN-THE-LOOP</p><h2>Exception queue</h2></div><span>{open.length} NEED ATTENTION</span></div>
          {open.length === 0 ? <div className="cleared"><ShieldCheck/><h3>Queue cleared</h3><p>All exceptions have a recorded control decision.</p></div> : open.slice(0,8).map(item=><article className="exception" key={item.id}>
            <div className="exception-top"><div><span className={`severity ${item.severity.toLowerCase()}`}>{item.severity}</span><strong>{item.exception_type.replaceAll('_',' ')}</strong></div><code>{item.id}</code></div>
            <div className="evidence"><div><span>PAYMENT</span><b>₹{item.evidence.payment_amount}</b></div><ArrowRight/><div><span>SETTLEMENT</span><b>{item.evidence.settlement_amount ? `₹${item.evidence.settlement_amount}`:'MISSING'}</b></div><ArrowRight/><div><span>BANK</span><b>{item.evidence.bank_amount ? `₹${item.evidence.bank_amount}`:'MISSING'}</b></div></div>
            <div className="ai"><Sparkles size={15}/><p><span>STRUCTURED ANALYSIS · {(Number(item.ai_confidence)*100).toFixed(0)}% CONFIDENCE</span>{item.ai_reason}</p></div>
            <div className="actions"><button onClick={()=>review(item.id,'REJECT')}><X size={15}/> Confirm exception</button><button className="approve" onClick={()=>review(item.id,'APPROVE')}><Check size={15}/> Approve match</button></div>
          </article>)}
        </div>
        <aside>
          <p className="eyebrow">CONTROL LOGIC</p><h2>Trust is earned<br/>in layers.</h2>
          <div className="layer"><b>01</b><div><strong>Exact reference</strong><span>Identity and amount equality</span></div><i>99%</i></div>
          <div className="layer"><b>02</b><div><strong>Fee-adjusted</strong><span>Gross less fee and tax</span></div><i>96%</i></div>
          <div className="layer"><b>03</b><div><strong>Rule evidence</strong><span>Merchant and date tolerance</span></div><i>82%</i></div>
          <div className="layer"><b>04</b><div><strong>Human control</strong><span>Ambiguous or high-risk</span></div><i>FINAL</i></div>
          <blockquote>“AI proposes. Policy gates. Humans decide.”</blockquote>
        </aside>
      </section>
    </>}
  </main>
}

function Metric({label,value,note,icon,alert=false}:{label:string,value:string,note:string,icon:React.ReactNode,alert?:boolean}) {
  return <div className={`metric ${alert?'alert':''}`}><div className="metric-label">{label}{icon}</div><strong>{value}</strong><span>{note}</span></div>
}
