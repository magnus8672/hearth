import { useEffect, useRef, useState } from 'react';
import { api, mutation, type Identity } from './api';

type Question = { id: string; kind: 'choice' | 'score' | 'boolean'; instructions: string; options?: Record<string, string>; rubric?: string[] };
type Answer = { id: string; kind: string; choice: string | null; score: number | null; probability_true: number | null; probabilities: Record<string, number> | null; answer_confidence: number | null; provider_confidence: number | null; abstained: boolean };
type Result = { model: string; model_revision: string; elapsed_ms: number; input_tokens: number; answers: Answer[] };
type Run = { id: string; state: string; request: { state: string; questions: Question[] }; receipt: { source: string }; result?: Result; reason?: string; cancel_requested?: boolean };
type Target = { id: string; name: string; model: string; ready: boolean };
type Builtin = { ready: boolean; model?: string; model_revision?: string; maximum_tokens?: number; reason?: string };
type Listing = { builtin: Builtin | null; targets: Target[]; items: Run[]; comparisons?: { metadata: Record<string, unknown>; created_at: string }[] };

function exportRun(run: Run) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(run, null, 2)], { type: 'application/json' }));
  const link = document.createElement('a'); link.href = url; link.download = `hearth-decision-${run.id}.json`; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function Decisions({ identity, onDirty }: { identity: Identity; onDirty: (dirty: boolean) => void }) {
  const [listing, setListing] = useState<Listing>({ builtin: null, targets: [], items: [] });
  const [state, setState] = useState('');
  const [question, setQuestion] = useState('');
  const [kind, setKind] = useState<Question['kind']>('choice');
  const [criteria, setCriteria] = useState('yes: Fits the requirement\nno: Does not fit the requirement');
  const [target, setTarget] = useState('builtin');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const pending = useRef<{ key: string; id: string } | null>(null);
  const active = listing.items.some(item => item.state === 'running');
  async function refresh() { setListing(await api<Listing>('/api/v1/decisions')); }
  useEffect(() => { void refresh().catch(reason => setError(reason.message)); }, []);
  useEffect(() => { if (!active) return; const timer = window.setInterval(() => void refresh().catch(reason => setError(reason.message)), 1000); return () => clearInterval(timer); }, [active]);
  useEffect(() => {
    const dirty = !!(state || question); onDirty(dirty);
    const warn = (event: BeforeUnloadEvent) => { if (dirty) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('beforeunload', warn);
    return () => { onDirty(false); window.removeEventListener('beforeunload', warn); };
  }, [state, question, onDirty]);
  async function send() {
    setError(''); setNotice(''); setBusy(true);
    try {
      const lines = criteria.split('\n').map(line => line.trim()).filter(Boolean);
      const q: Question = { id: 'answer', kind, instructions: question };
      if (kind === 'score') q.rubric = lines;
      if (kind === 'choice') {
        q.options = {};
        for (const line of lines) {
          const colon = line.indexOf(':'); const id = line.slice(0, colon).trim();
          if (colon < 1 || !/^[a-z][a-z0-9_.-]{0,79}$/.test(id) || id in q.options) throw new Error('Use one unique option_id: description per line.');
          q.options[id] = line.slice(colon + 1).trim();
        }
      }
      const payload = { state, questions: [q], target_id: ['builtin', 'assigned'].includes(target) ? null : target, use_route: target === 'assigned' };
      const key = JSON.stringify(payload);
      if (pending.current?.key !== key) pending.current = { key, id: crypto.randomUUID() };
      await api('/api/v1/decisions', mutation(identity, { ...payload, id: pending.current.id }));
      await refresh(); pending.current = null; setNotice('Decision submitted. Keep this input to compare another provider.');
    } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); }
  }
  return <><div className="info-banner"><p>Your input and results stay in your private workspace. A decision selects or scores an answer; it never executes an action. Probabilities are model estimates, not guarantees.</p></div>
    <div className="decision-layout"><form className="panel decision-form" onSubmit={event => { event.preventDefault(); void send(); }}>
      <h2>Give a question some structure.</h2>
      <label>Decision provider<select value={target} onChange={event => setTarget(event.target.value)} disabled={busy}>
        <option value="builtin" disabled={!listing.builtin?.ready}>Built-in Laya{listing.builtin?.ready ? '' : ' · unavailable'}</option>
        <option value="assigned" disabled={!listing.targets.some(item => item.ready)}>Assigned decision providers · use route policy</option>
        {listing.targets.map(item => <option key={item.id} value={item.id} disabled={!item.ready}>{item.name} · {item.model}{item.ready ? '' : ' · needs verification'}</option>)}</select></label>
      <p className="small-copy">Choosing a provider here does not change internal routing. Each result records the provider that answered.</p>
      <label>State or source text<textarea value={state} maxLength={8000} required onChange={event => setState(event.target.value)} /></label>
      <label>Question type<select value={kind} onChange={event => { setKind(event.target.value as Question['kind']); setCriteria(event.target.value === 'score' ? 'Needs work\nAdequate\nExcellent' : 'yes: Fits the requirement\nno: Does not fit the requirement'); }}><option value="choice">Choice</option><option value="score">Score against a rubric</option><option value="boolean">Boolean probability</option></select></label>
      <label>Question<input value={question} maxLength={800} required onChange={event => setQuestion(event.target.value)} /></label>
      {kind !== 'boolean' && <label>{kind === 'choice' ? 'Options, one option_id: description per line' : 'Rubric, lowest to highest, one level per line'}<textarea value={criteria} onChange={event => setCriteria(event.target.value)} maxLength={3500} required /></label>}
      <p className="small-copy">Up to 16 choices or rubric levels. Inputs that exceed the checkpoint context are rejected without silently shortening them.</p>
      <button className="primary-button" disabled={busy || active || !state.trim() || !question.trim() || (target === 'builtin' && !listing.builtin?.ready)}>{busy ? 'Submitting…' : 'Evaluate decision'}</button>
      {notice && <p role="status">{notice}</p>}{error && <p className="error-notice" role="alert">{error}</p>}
    </form><section aria-label="Decision results"><div className="section-heading"><h2>Your decisions</h2><button className="quiet-button" onClick={() => void refresh().catch(reason => setError(reason.message))}>Refresh</button></div>
      {!listing.items.length && <div className="panel"><p>Your private results will appear here.</p></div>}
      {listing.items.map(run => <article className="panel decision-result" key={run.id}><h3>{run.request.questions[0].instructions}</h3><p className="small-copy">{run.result?.model || run.receipt.source} · {run.cancel_requested && run.state === 'running' ? 'Stopping; waiting for the current evaluation to finish' : run.state}</p>
        {run.result?.answers.map(answer => { const q = run.request.questions.find(item => item.id === answer.id)!; return <div key={answer.id}>
          <strong>{answer.abstained ? 'The provider abstained.' : answer.kind === 'choice' ? `${answer.choice}: ${q.options?.[answer.choice!] || ''}` : answer.kind === 'score' ? `Expected rubric index: ${answer.score?.toFixed(2)} / ${(q.rubric?.length || 1)-1}` : `Probability of true: ${((answer.probability_true || 0)*100).toFixed(1)}%`}</strong>
          {q.rubric && <ol start={0}>{q.rubric.map((level, index) => <li key={index}>{level}</li>)}</ol>}
          {answer.probabilities && <dl className="decision-probabilities">{Object.entries(answer.probabilities).map(([key, probability]) => <div key={key}><dt>{q.options?.[key] || q.rubric?.[Number(key)] || key}</dt><dd><meter min={0} max={1} value={probability} /> {(probability*100).toFixed(1)}%</dd></div>)}</dl>}
          <p className="small-copy">Answer confidence: {answer.answer_confidence === null ? 'unavailable' : `${(answer.answer_confidence*100).toFixed(1)}%`}. Provider confidence: {answer.provider_confidence === null ? 'unavailable' : answer.provider_confidence.toFixed(4)}.</p>
        </div>; })}
        {run.reason && <p className="error-notice">{run.reason}</p>}
        {run.result && <p className="small-copy">{run.result.elapsed_ms.toFixed(0)} ms · {run.result.input_tokens} input tokens · revision {run.result.model_revision}</p>}
        <details><summary>Input and receipt</summary><pre className="decision-json">{JSON.stringify(run, null, 2)}</pre></details>
        <div className="target-actions"><button className="quiet-button" onClick={() => exportRun(run)}>Save JSON</button><button className="quiet-button" disabled={busy || !!run.cancel_requested && run.state === 'running'} onClick={async () => { setBusy(true); try { await api(`/api/v1/decisions/${run.id}`, mutation(identity, undefined, 'DELETE')); await refresh(); } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); } }}>{run.state === 'running' ? 'Stop decision' : 'Delete'}</button></div>
      </article>)}
      {!!listing.comparisons?.length && <details className="panel"><summary>Your recent routing comparisons</summary><p className="small-copy">Background observations for your requests only. Comparisons do not execute another reply.</p><pre className="decision-json">{JSON.stringify(listing.comparisons, null, 2)}</pre></details>}
    </section></div></>;
}

type Configuration = { revision: number; mode: 'legacy' | 'shadow' | 'semantic'; source: 'builtin' | 'dedicated'; target_id: string | null; fallback_builtin: boolean; member_builtin: boolean; threshold: number; deadline_ms: number; shadow_sample: number };
export function DecisionSettings({ identity, onDirty }: { identity: Identity; onDirty: (dirty: boolean) => void }) {
  const [baseline, setBaseline] = useState('');
  const [config, setConfig] = useState<Configuration | null>(null);
  const [builtin, setBuiltin] = useState<Builtin | null>(null);
  const [targets, setTargets] = useState<Target[]>([]);
  const [error, setError] = useState(''); const [notice, setNotice] = useState(''); const [busy, setBusy] = useState(false);
  async function refresh() { const value = await api<{ settings: Configuration; builtin: Builtin; targets: Target[] }>('/api/v1/decision-settings'); setConfig(value.settings); setBaseline(JSON.stringify(value.settings)); setBuiltin(value.builtin); setTargets(value.targets); }
  useEffect(() => { void refresh().catch(reason => setError(reason.message)); }, []);
  useEffect(() => {
    const dirty = !!config && JSON.stringify(config) !== baseline; onDirty(dirty);
    const warn = (event: BeforeUnloadEvent) => { if (dirty) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('beforeunload', warn);
    return () => { onDirty(false); window.removeEventListener('beforeunload', warn); };
  }, [config, baseline, onDirty]);
  return <section className="panel decision-form"><h2>Routing and decisions</h2><p>Internal routing and member experiments have independent assignments. Existing explicit actions bypass the intent classifier.</p>
    <p className="small-copy">Semantic routing is experimental and stays opt-in. The English checkpoint did not meet the current accuracy, coverage or latency targets. Begin with background comparison; use Legacy to roll back.</p><p>Built-in Laya: <strong>{builtin?.ready ? 'Ready' : 'Unavailable'}</strong>{builtin?.model ? ` · ${builtin.model}` : ''}</p>{builtin?.reason && <p>{builtin.reason}</p>}
    {config && <form onSubmit={async event => { event.preventDefault(); setBusy(true); setError(''); setNotice(''); try { const saved = await api<Configuration>('/api/v1/decision-settings', mutation(identity, config, 'PUT')); setConfig(saved); setBaseline(JSON.stringify(saved)); setNotice('Saved for new requests. Member provider assignments are unchanged.'); } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); } }}>
      <label>Automatic routing<select value={config.mode} onChange={e => setConfig({ ...config, mode: e.target.value as Configuration['mode'] })}><option value="legacy">Legacy direct rules · rollback</option><option value="shadow">Compare decisions in background · keep legacy routing</option><option value="semantic">Semantic decisions for unresolved requests</option></select></label>
      <label>Internal decision source<select value={config.source} onChange={e => setConfig({ ...config, source: e.target.value as Configuration['source'] })}><option value="builtin">Built-in Laya on the head</option><option value="dedicated">Dedicated decision capability target</option></select></label>
      {config.source === 'dedicated' && <><label>Dedicated target<select value={config.target_id || ''} required onChange={e => setConfig({ ...config, target_id: e.target.value })}><option value="">Choose a verified target</option>{targets.map(t => <option value={t.id} key={t.id} disabled={!t.ready}>{t.name} · {t.model}{t.ready ? '' : ' · needs verification'}</option>)}</select></label><label className="checkbox-label"><input type="checkbox" checked={config.fallback_builtin} onChange={e => setConfig({ ...config, fallback_builtin: e.target.checked })} />Fall back to built-in Laya within the routing deadline</label></>}
      <p className="small-copy">Register dedicated services in Providers using hearth decision provider, verify them, then assign them to Decisions. Switching this source retains the built-in service and member assignments.</p>
      <label>Minimum answer confidence<input type="number" min={0} max={1} step={0.01} value={config.threshold} onChange={e => setConfig({ ...config, threshold: Number(e.target.value) })} /></label>
      <label>Routing deadline (milliseconds)<input type="number" min={100} max={10000} step={100} value={config.deadline_ms} onChange={e => setConfig({ ...config, deadline_ms: Number(e.target.value) })} /></label>
      <label>Background comparison sample (%)<input type="number" min={0} max={100} value={config.shadow_sample} onChange={e => setConfig({ ...config, shadow_sample: Number(e.target.value) })} /></label>
      <label className="checkbox-label"><input type="checkbox" checked={config.member_builtin} onChange={e => setConfig({ ...config, member_builtin: e.target.checked })} />Allow members with Decisions permission to use built-in Laya</label>
      <p className="small-copy">Confidence needs calibration for each checkpoint and question. Uncertain semantic requests ask for clarification. Balanced provider selection is configured separately on each text or Decisions capability route.</p>
      <div className="target-actions"><button className="primary-button" disabled={busy}>Save decision settings</button><button type="button" className="quiet-button" disabled={busy} onClick={() => void refresh().catch(reason => setError(reason.message))}>Reload</button></div>
    </form>}{notice && <p role="status">{notice}</p>}{error && <p className="error-notice" role="alert">{error}</p>}</section>;
}
