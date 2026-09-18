import { useEffect, useState } from 'react';
import { api, mutation, type Identity } from './api';

type Worker = { id: string; name: string; pool_name: string; online: boolean; state: string; reason: string; policy: 'resident' | 'shared'; paused: boolean; revoked: boolean; revision: number; desired_service: string | null; ready_service: string | null; active_run_id: string | null; execution_state: string; queued: number; services: Record<string, { name: string; connection_id: string }> };

export function Workers({ identity }: { identity: Identity }) {
  const [items, setItems] = useState<Worker[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const canOperate = identity.permissions.includes('node.operate');
  const canAssign = identity.permissions.includes('node.assign');
  async function refresh() { setItems((await api<{ items: Worker[] }>('/api/v1/workers')).items); }
  useEffect(() => { void refresh().catch(reason => setError(reason.message)); const timer = setInterval(() => void refresh().catch(reason => setError(reason.message)), 3000); return () => clearInterval(timer); }, []);
  async function change(worker: Worker, updates: Partial<Worker>) {
    setBusy(true); setError('');
    try { await api(`/api/v1/workers/${worker.id}`, mutation(identity, { revision: worker.revision, paused: worker.paused, policy: worker.policy, desired_service: worker.desired_service, ...updates }, 'PUT')); await refresh(); }
    catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  }
  return <><div className="info-banner"><p>Keep specialists resident for quick replies. On a shared GPU, hearth can finish one job, stop its service, and prepare the next approved service. Pausing lets active work finish and holds the queue.</p></div>
    {error && <p className="error-notice" role="alert">{error}</p>}
    {!items.length && <section className="panel"><h2>No managed workers yet.</h2><p>Adopt an installed Linux service with the worker setup tool. Existing providers continue to work independently.</p></section>}
    <div className="catalog-grid">{items.map(worker => <section className="panel" key={worker.id}><div className="section-heading"><h2>{worker.name}</h2><strong>{worker.online ? worker.state : 'Offline'}</strong></div><p>{worker.pool_name}</p><dl><dt>Ready service</dt><dd>{worker.ready_service ? worker.services[worker.ready_service]?.name : 'None yet'}</dd><dt>GPU work</dt><dd>{worker.execution_state} · {worker.queued} waiting</dd><dt>Admission</dt><dd>{worker.paused ? 'Paused' : 'Accepting work'}</dd></dl>
      <label>GPU policy<select aria-label="GPU policy" value={worker.policy} disabled={busy || !canAssign || !!worker.active_run_id || worker.revoked} onChange={event => { const policy = event.target.value as Worker['policy']; if (policy !== 'shared' || window.confirm('Allow this GPU to switch between its approved services when queued jobs need them? Switching adds startup time.')) void change(worker, { policy }); }}><option value="resident">Keep the selected service resident</option><option value="shared">Share this GPU between services</option></select></label>
      <label>Selected service<select aria-label="Selected service" value={worker.desired_service || ''} disabled={busy || !canAssign || !!worker.active_run_id || worker.revoked} onChange={event => void change(worker, { desired_service: event.target.value || null, ...(!event.target.value ? { paused: true } : {}) })}><option value="">Unload and pause</option>{Object.entries(worker.services).map(([id, service]) => <option key={id} value={id}>{service.name}</option>)}</select></label>
      <div className="target-actions"><button className="quiet-button" disabled={busy || !canOperate || worker.revoked || !worker.desired_service} onClick={() => void change(worker, { paused: !worker.paused })}>{worker.paused ? 'Resume queue' : 'Pause queue'}</button>{worker.state === 'failed' && <button className="quiet-button" disabled={busy || !canAssign || !!worker.active_run_id || worker.revoked} onClick={() => void change(worker, {})}>Retry service</button>}</div>
      {worker.reason && <p className="small-copy">{worker.reason.replaceAll('_', ' ')}</p>}{worker.active_run_id && <p className="small-copy">Service changes are available after the active job releases this GPU. Uncertain work stays reserved until its provider is confirmed idle.</p>}</section>)}</div></>;
}
