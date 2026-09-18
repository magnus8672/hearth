import { useEffect, useRef, useState } from 'react';
import { api, mutation, type Identity } from './api';
import { Icon } from './index';

type Target = { id: string; name: string; model_id: string; ready: boolean };
type Parameters = { id: string; model: string; prompt: string; negative_prompt: string; shape: 'square' | 'landscape' | 'portrait'; steps: 20 | 30 | 40; seed: number };
type Job = { id: string; target_id: string; request: Parameters; status: string; progress: number; cancel_requested: boolean; reason: string | null; metadata: { width: number; height: number; model_revision: string; sha256: string } | null };

export function Images({ identity, onDirty }: { identity: Identity; onDirty: (dirty: boolean) => void }) {
  const [targets, setTargets] = useState<Target[]>([]);
  const [target, setTarget] = useState('');
  const [jobs, setJobs] = useState<Job[]>([]);
  const [prompt, setPrompt] = useState('');
  const [negative, setNegative] = useState('');
  const [shape, setShape] = useState<Parameters['shape']>('square');
  const [steps, setSteps] = useState<Parameters['steps']>(20);
  const [seed, setSeed] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [deleting, setDeleting] = useState<string | null>(null);
  const [notice, setNotice] = useState('');
  const removed = useRef(new Set<string>());
  const deletingNow = useRef(false);
  const pending = useRef<{ signature: string; data: Parameters } | null>(null);
  const sending = useRef(false);
  const dirty = !!prompt.trim() || !!negative.trim();
  const selected = targets.find(item => item.id === target);
  const running = jobs.some(job => ['queued', 'running'].includes(job.status));
  useEffect(() => { onDirty(dirty); return () => onDirty(false); }, [dirty, onDirty]);
  useEffect(() => {
    const listener = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); };
    window.addEventListener('beforeunload', listener);
    return () => window.removeEventListener('beforeunload', listener);
  }, [dirty]);
  async function refresh() {
    const result = await api<{ items: Target[] }>('/api/v1/image-targets');
    setTargets(result.items); setTarget(previous => previous || result.items[0]?.id || '');
    setJobs((await api<{ items: Job[] }>('/api/v1/images')).items.filter(job => !removed.current.has(job.id)));
  }
  useEffect(() => { void refresh().catch(reason => setError(reason.message)); }, []);
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    async function poll() {
      try {
        const result = await api<{ items: Job[] }>('/api/v1/images', { signal: controller.signal });
        if (!disposed) { setJobs(result.items.filter(job => !removed.current.has(job.id))); timer = setTimeout(() => void poll(), result.items.some(job => ['queued', 'running'].includes(job.status)) ? 700 : 5000); }
      } catch (reason) { if (!disposed) setError((reason as Error).message); }
    }
    void poll();
    return () => { disposed = true; controller.abort(); clearTimeout(timer); };
  }, []);
  async function deleteImage(job: Job) {
    if (deletingNow.current || !window.confirm('Delete this image from your gallery and any private chat where it appears? This cannot be undone.')) return;
    deletingNow.current = true; setDeleting(job.id); setError(''); setNotice('');
    try {
      await api(`/api/v1/images/${job.id}`, mutation(identity, undefined, 'DELETE'));
      removed.current.add(job.id);
      setJobs(previous => previous.filter(item => item.id !== job.id));
      setNotice('Image deleted.');
    } catch (reason) { setError((reason as Error).message); }
    finally { deletingNow.current = false; setDeleting(null); }
  }
  async function generate() {
    if (!selected?.ready || !prompt.trim() || sending.current || running) return;
    const number = seed.trim() ? Number(seed) : undefined;
    if (number !== undefined && (!Number.isInteger(number) || number < 0 || number > 4294967295)) { setError('Use a seed from 0 to 4,294,967,295, or leave it blank.'); return; }
    sending.current = true; setBusy(true); setError('');
    try {
      const signature = JSON.stringify({ target, prompt, negative, shape, steps, seed });
      if (pending.current?.signature !== signature) pending.current = { signature, data: { id: crypto.randomUUID(), model: selected.model_id, prompt, negative_prompt: negative, shape, steps, seed: number ?? crypto.getRandomValues(new Uint32Array(1))[0] } };
      await api('/api/v1/images', mutation(identity, { target_id: target, request: pending.current.data }));
      pending.current = null; setPrompt(''); setNegative(''); await refresh();
    } catch (reason) { setError((reason as Error).message); } finally { sending.current = false; setBusy(false); }
  }
  return <><div className="info-banner"><Icon name="lock" /><p>Images belong to your private workspace. Your selected local provider receives the prompt. This first image profile creates pictures from text; image editing and 3D generation are still being built.</p></div><div className="image-layout"><section className="panel image-form"><h2>Picture something.</h2><form onSubmit={event => { event.preventDefault(); void generate(); }}>
    <label>Image model<select value={target} onChange={event => setTarget(event.target.value)} disabled={busy}>{!targets.length && <option value="">No image provider assigned</option>}{targets.map(item => <option key={item.id} value={item.id}>{item.name}{item.ready ? '' : ' · Needs verification'}</option>)}</select></label>
    <label htmlFor="image-prompt">Describe your image</label><textarea id="image-prompt" value={prompt} maxLength={1000} disabled={busy} onChange={event => setPrompt(event.target.value)} placeholder="A cozy stone cottage beneath the pines, warm windows, storybook illustration…" /><p className="small-copy">A short description works best. SDXL supports about 60 words, depending on the words you choose.</p>
    <details><summary>Things to leave out</summary><label className="sr-only" htmlFor="image-negative">Negative prompt</label><textarea id="image-negative" value={negative} maxLength={1000} onChange={event => setNegative(event.target.value)} placeholder="Optional: text, watermark, blur…" /></details>
    <div className="image-settings"><label>Shape<select value={shape} onChange={event => setShape(event.target.value as Parameters['shape'])}><option value="square">Square · 1024 × 1024</option><option value="landscape">Landscape · 1024 × 768</option><option value="portrait">Portrait · 768 × 1024</option></select></label><label>Detail passes<select value={steps} onChange={event => setSteps(Number(event.target.value) as Parameters['steps'])}><option value={20}>20 · Quick sketch</option><option value={30}>30 · A little more detail</option><option value={40}>40 · Take your time</option></select></label></div>
    <label>Seed <span className="muted">optional</span><input inputMode="numeric" value={seed} onChange={event => setSeed(event.target.value)} placeholder="Choose one for me" maxLength={10} /></label><p className="small-copy">The seed and model version are saved with every image so you can reuse the same settings.</p>
    <button className="primary-button" disabled={busy || running || !selected?.ready || !prompt.trim()}>{busy ? 'Saving request…' : running ? 'An image is taking shape…' : 'Create image'}</button></form>{!selected?.ready && <p className="small-copy">Connect and verify an image provider in Administration, then refresh this page.</p>}</section>
    <section aria-label="Your images"><div className="section-heading"><h2>Your little gallery</h2><button className="quiet-button" onClick={() => void refresh().catch(reason => setError(reason.message))}>Refresh</button></div>{error && <p className="error-notice" role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}{!jobs.length && <div className="panel chat-empty"><Icon name="image" /><h3>From a few words to a picture.</h3><p>Your images, seeds and descriptions will be saved here.</p></div>}<div className="image-gallery">{jobs.map(job => <article key={job.id} className="panel image-card">{job.status === 'completed' ? <a href={`/api/v1/images/${job.id}/image`} target="_blank" rel="noreferrer"><img src={`/api/v1/images/${job.id}/image`} alt={job.request.prompt} loading="lazy" /></a> : <div className="image-placeholder"><Icon name="image" /><strong>{job.status === 'running' ? job.cancel_requested ? 'Stopping…' : 'Taking shape…' : job.status}</strong>{job.status === 'running' && <><progress max={job.request.steps} value={job.progress} aria-label="Image generation progress" /><span>{job.progress} / {job.request.steps} passes</span><button className="quiet-button" disabled={job.cancel_requested} onClick={() => void api(`/api/v1/images/${job.id}/cancel`, mutation(identity)).then(refresh).catch(reason => setError(reason.message))}>Stop image</button></>}</div>}<p>{job.request.prompt}</p><p className="small-copy">Seed {job.request.seed} · {job.request.steps} passes · {job.request.shape}</p>{job.reason && <p className="small-copy">{job.reason}</p>}<div className="target-actions">{job.status === 'completed' && <a className="quiet-button button-link" href={`/api/v1/images/${job.id}/image`} download={`hearth-${job.id}.png`}>Save PNG</a>}<button className="quiet-button" disabled={busy} onClick={() => { if (dirty && !window.confirm('Replace your unsent image description with these saved settings?')) return; setTarget(job.target_id); setPrompt(job.request.prompt); setNegative(job.request.negative_prompt); setShape(job.request.shape); setSteps(job.request.steps); setSeed(String(job.request.seed)); }}>Use settings</button>{!['queued', 'running'].includes(job.status) && <button className="quiet-button" disabled={deleting !== null} onClick={() => void deleteImage(job)}>{deleting === job.id ? 'Deleting…' : 'Delete image'}</button>}</div></article>)}</div></section></div></>;
}
