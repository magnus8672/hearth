import { lazy, Suspense, useEffect, useState } from 'react';
import { Workspace } from './workspace';
import { api, mutation, type Identity } from './api';
import { geometryReference, prepareGeometryReference } from './geometry-reference';
import { GeometrySettings, SavedGeometrySettings, tuningDefaults, type TuningProfile, type TuningValues } from './geometry-settings';
const Preview = lazy(() => import('./geometry-preview'));
type Target = { id: string; name: string; model_id: string; state: string; profile: { resolutions?: number[]; tuning?: TuningProfile | null } };
type Job = { id: string; name: string; has_thumbnail: boolean; status: string; reason: string | null; cancel_requested: boolean; request: { model: string; resolution: number; seed: number; trellis?: TuningValues; hunyuan?: TuningValues }; metadata: { triangles: number; textures: number; bytes: number } | null };

export function Geometry({ identity, onDirty }: { identity: Identity; onDirty: (dirty: boolean) => void }) {
  const [targets, setTargets] = useState<Target[]>([]); const [targetId, setTarget] = useState('');
  const [jobs, setJobs] = useState<Job[]>([]); const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState(''); const [editing, setEditing] = useState(''); const [renameName, setRenameName] = useState(''); const [renaming, setRenaming] = useState(false);
  const [resolution, setResolution] = useState(512); const [seed, setSeed] = useState('');
  const [tuning, setTuning] = useState<Record<TuningProfile, TuningValues>>(() => ({ 'trellis-v1': tuningDefaults('trellis-v1'), 'hunyuan-v1': tuningDefaults('hunyuan-v1') }));
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [preview, setPreview] = useState('');
  const [source, setSource] = useState(() => geometryReference(window.location.hash));
  const [sourceLoading, setSourceLoading] = useState(false); const [referenceUrl, setReferenceUrl] = useState('');
  const target = targets.find(item => item.id === targetId);
  const waiting = jobs.filter(item => ['queued', 'running'].includes(item.status)).length;
  useEffect(() => {
    const supported = target?.profile.resolutions || [512];
    if (!supported.includes(resolution)) setResolution(supported[0]);
  }, [target, resolution]);
  async function refresh() { const result = await api<{ items: Job[] }>('/api/v1/geometry'); setJobs(result.items); }
  useEffect(() => {
    api<{ items: Target[] }>('/api/v1/geometry-targets').then(result => { setTargets(result.items); setTarget(result.items.find(item => item.state === 'ready')?.id || ''); }).catch(reason => setError(reason.message));
    void refresh().catch(reason => setError(reason.message));
    const timer = window.setInterval(() => { void refresh().catch(reason => setError(reason.message)); }, 2000);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => {
    const changed = () => setSource(geometryReference(window.location.hash));
    window.addEventListener('hashchange', changed); window.addEventListener('popstate', changed);
    return () => { window.removeEventListener('hashchange', changed); window.removeEventListener('popstate', changed); };
  }, []);
  useEffect(() => {
    if (!source) { setSourceLoading(false); return; }
    const controller = new AbortController(); let disposed = false;
    const [kind, id] = source.split('/');
    setFile(null); setError(''); setSourceLoading(true);
    fetch(`/api/v1/${kind === 'conversation' ? 'conversation-images' : 'images'}/${id}/image`, { credentials: 'same-origin', cache: 'no-store', signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error('The selected image is no longer available to you. Choose another reference.');
        return prepareGeometryReference(await response.blob());
      }).then(reference => { if (!disposed) setFile(reference); })
      .catch(reason => { if (!disposed) setError(reason.message || 'The selected image could not be opened.'); })
      .finally(() => { if (!disposed) setSourceLoading(false); });
    return () => { disposed = true; controller.abort(); };
  }, [source]);
  useEffect(() => {
    if (!file) { setReferenceUrl(''); return; }
    const url = URL.createObjectURL(file); setReferenceUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  useEffect(() => { onDirty(!!file || !!name || !!editing); return () => onDirty(false); }, [file, name, editing, onDirty]);
  async function generate() {
    if (!file || !target || !name.trim() || busy || sourceLoading) return;
    setBusy(true); setError('');
    try {
      if (file.size > 8 * 1024 * 1024) throw new Error('Choose an image smaller than 8 MB.');
      const bytes = await file.arrayBuffer();
      const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(x => x.toString(16).padStart(2, '0')).join('');
      const encoded = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(',')[1]); reader.onerror = reject; reader.readAsDataURL(file); });
      const options = target.profile.tuning ? { [target.profile.tuning === 'trellis-v1' ? 'trellis' : 'hunyuan']: tuning[target.profile.tuning] } : {};
      await api('/api/v1/geometry', mutation(identity, { name: name.trim(), target_id: target.id, image: encoded, request: { schema_version: 1, id: crypto.randomUUID(), model: target.model_id, image_sha256: digest, resolution, seed: seed ? Number(seed) : crypto.getRandomValues(new Uint32Array(1))[0] % 2147483648, ...options } }));
      setFile(null); setName(''); await refresh();
    } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); }
  }
  async function rename(job: Job) {
    if (!renameName.trim() || renaming) return;
    setRenaming(true); setError('');
    try {
      await api(`/api/v1/geometry/${job.id}`, mutation(identity, { name: renameName.trim() }, 'PATCH'));
      setEditing(''); await refresh();
    } catch (reason) { setError((reason as Error).message); } finally { setRenaming(false); }
  }
  async function action(job: Job, remove: boolean) {
    if (remove && !window.confirm('Delete this saved 3D model from your workspace?')) return;
    setError('');
    try { await api(`/api/v1/geometry/${job.id}${remove ? '' : '/cancel'}`, mutation(identity, undefined, remove ? 'DELETE' : 'POST')); if (remove) { if (editing === job.id) setEditing(''); if (preview === job.id) setPreview(''); } await refresh(); }
    catch (reason) { setError((reason as Error).message); }
  }
  return <><div className="info-banner"><p>Your image and model stay on your farm. Use a clear picture of one object. The unseen sides are inferred, and the result may need cleanup in a 3D editor.</p></div>
    {error && <p className="error-notice" role="alert">{error}</p>}
    <Workspace name="geometry" owner={identity.id} leftLabel="model settings"><section className="panel"><h2>Give an image a new dimension.</h2><form className="image-form" onSubmit={event => { event.preventDefault(); void generate(); }}>
      <label>Model name<input required maxLength={120} value={name} onChange={event => setName(event.target.value)} placeholder="For example, Desert scout" disabled={busy} /></label>
      <label>3D model provider<select value={targetId} onChange={event => setTarget(event.target.value)} required><option value="">Choose a verified provider</option>{targets.map(item => <option key={item.id} value={item.id} disabled={item.state !== 'ready'}>{item.name} · {item.model_id}</option>)}</select></label>
      {!targets.length && <p className="small-copy">Ask your administrator to connect and verify a geometry provider.</p>}
      <label>Reference image<input key={file?.name || 'unselected'} type="file" accept="image/png,image/jpeg,image/webp" onChange={event => setFile(event.target.files?.[0] || null)} disabled={busy || sourceLoading} /></label>
      {sourceLoading && <p role="status">Preparing your selected image…</p>}
      {referenceUrl && <img className="geometry-reference" src={referenceUrl} alt="Reference for your 3D model" />}
      {file && <p>{file.name} · {(file.size / 1024 / 1024).toFixed(1)} MB</p>}
      {source && file && <p className="small-copy">Your selected image is ready. The original stays unchanged; this model will be saved privately to your workspace.</p>}
      {target?.profile.tuning !== 'hunyuan-v1' && <label>Geometry detail<select value={resolution} onChange={event => setResolution(Number(event.target.value))}>{(target?.profile.resolutions || [512]).map(value => <option key={value} value={value}>{value === 512 ? 'Standard · 512' : 'Detailed · 1024'}</option>)}</select></label>}
      <p className="small-copy">Jobs share the GPU queue with image generation. Textures are included by default.</p>
      <label>Seed <span className="muted">optional</span><input type="number" min="0" max="2147483647" step="1" placeholder="Choose one for me" value={seed} onChange={event => setSeed(event.target.value)} /></label>
      {target?.profile.tuning ? <GeometrySettings profile={target.profile.tuning} values={tuning[target.profile.tuning]} disabled={busy} onChange={values => setTuning(previous => ({ ...previous, [target.profile.tuning!]: values }))} /> : target && <p className="small-copy">This provider uses its verified defaults. Tuning controls become available after an administrator updates and verifies its adapter.</p>}
      <button className="primary-button" disabled={busy || sourceLoading || !name.trim() || !file || !target || waiting >= 8}>{busy ? 'Adding to queue…' : 'Create 3D model'}</button>
    </form></section><section><div className="section-heading"><h2>Your models</h2><span>{waiting ? `${waiting} waiting or running` : 'Private to you'}</span></div>
      {!jobs.length && <div className="panel"><p>Your finished models will appear here.</p></div>}
      <div className="geometry-gallery">{jobs.map(job => <article className={`panel geometry-card ${preview === job.id ? 'preview-open' : ''}`} key={job.id}><div className="section-heading"><h3>{job.name}</h3><span>{job.status}</span></div><p className="small-copy">{job.request.model} · Detail {job.request.hunyuan?.octree_resolution ?? job.request.resolution} · seed {job.request.seed}</p>
        <SavedGeometrySettings trellis={job.request.trellis} hunyuan={job.request.hunyuan} />
        {editing === job.id ? <form className="geometry-rename" onSubmit={event => { event.preventDefault(); void rename(job); }}>
          <label>New model name<input autoFocus required maxLength={120} value={renameName} onChange={event => setRenameName(event.target.value)} disabled={renaming} /></label>
          <div className="target-actions"><button className="quiet-button" disabled={renaming || !renameName.trim()}>{renaming ? 'Saving…' : 'Save name'}</button><button type="button" className="quiet-button" disabled={renaming} onClick={() => setEditing('')}>Cancel rename</button></div>
        </form> : <button className="quiet-button" disabled={renaming} onClick={() => { setEditing(job.id); setRenameName(job.name); }}>Rename</button>}
        {job.has_thumbnail ? <figure className="geometry-thumbnail"><img loading="lazy" src={`/api/v1/geometry/${job.id}/thumbnail`} alt={`Reference for ${job.name}`} /><figcaption>Reference image</figcaption></figure> : <p className="geometry-thumbnail-empty small-copy">No saved reference preview</p>}
        {job.reason && <p role="status">{job.reason}</p>}{job.status === 'running' && <p role="status">Building your model. This can take several minutes.</p>}
        {job.metadata && <p>{job.metadata.triangles.toLocaleString()} triangles · {job.metadata.textures} textures · {(job.metadata.bytes / 1024 / 1024).toFixed(1)} MB</p>}
        {preview === job.id && job.status === 'completed' && <Suspense fallback={<p>Opening preview…</p>}><Preview id={job.id} /></Suspense>}
        <div className="target-actions">{job.status === 'completed' && <><button className="quiet-button" onClick={() => setPreview(preview === job.id ? '' : job.id)}>{preview === job.id ? 'Close preview' : 'Preview 3D'}</button><a className="quiet-button button-link" href={`/api/v1/geometry/${job.id}/model`} download>Save GLB</a></>}
          {['queued', 'running'].includes(job.status) ? <button className="quiet-button" disabled={job.cancel_requested} onClick={() => void action(job, false)}>{job.cancel_requested ? 'Stopping…' : 'Cancel'}</button> : <button className="quiet-button" onClick={() => void action(job, true)}>Delete model</button>}</div>
      </article>)}</div>
    </section></Workspace></>;
}
