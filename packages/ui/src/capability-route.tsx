import { useEffect, useState } from 'react';
import { api, mutation, type Identity } from './api';

type Binding = { target_id: string; priority: number; ready: boolean; reason: string };
type Route = { capability_id: string; display_name: string; revision: number; profile: { builtin?: boolean; protocol: string; executable: boolean; scope: string }; targets: Binding[] };
type Model = { base_url?: string; pool_name?: string; id: string; name: string; model_id: string; protocol?: string; revision: number; active_run_id: string | null };

export function CapabilityRoute({ identity, selected, models, refreshKey, verify }: { identity: Identity; selected?: string; models: Model[]; refreshKey: number; verify: (model: Model, capability?: string) => Promise<void> }) {
  const [routes, setRoutes] = useState<Route[]>([]);
  const [choice, setChoice] = useState(selected || 'chat.general');
  const [targets, setTargets] = useState<string[]>([]);
  const [revision, setRevision] = useState(1);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const route = routes.find(item => item.capability_id === choice);
  async function refresh() { const data = await api<{ items: Route[] }>('/api/v1/capability-routes'); setRoutes(data.items.filter(item => !item.profile.builtin)); return data.items; }
  useEffect(() => { void refresh().catch(reason => setError(reason.message)); }, [refreshKey]);
  useEffect(() => { if (selected) { setChoice(selected); setDirty(false); } }, [selected]);
  useEffect(() => { if (route && !dirty) { setTargets(route.targets.map(item => item.target_id)); setRevision(route.revision); } }, [route, dirty]);
  useEffect(() => { const guard = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); }; window.addEventListener('beforeunload', guard); return () => window.removeEventListener('beforeunload', guard); }, [dirty]);
  function change(next: string[]) { setTargets(next); setDirty(true); setNotice(''); }
  return <section className="panel route-editor" aria-label="Capability assignment"><div className="section-heading"><h2>Give each capability a home</h2><button className="quiet-button" disabled={busy} onClick={() => { if (!dirty || window.confirm('Discard these unsaved route changes?')) { setDirty(false); void refresh().catch(reason => setError(reason.message)); } }}>Reload routes</button></div>
    <label>Capability<select aria-label="Capability" value={choice} disabled={busy || !!selected} onChange={event => { if (!dirty || window.confirm('Discard these unsaved route changes?')) { setChoice(event.target.value); setDirty(false); setError(''); setNotice(''); } }}>{routes.map(item => <option key={item.capability_id} value={item.capability_id}>{item.display_name}</option>)}</select></label>
    {route && <><p>{route.profile.scope}</p>{!route.profile.executable && <p className="small-copy">You can save its intended providers now. This route stays pending until its adapter and feature probe are available.</p>}
      <p className="small-copy">The first verified, idle model in this order receives a new request. Models sharing a GPU must use the same resource group. A failed or interrupted generation is never retried on another model automatically.</p>
      <ol className="route-targets">{targets.map((id, index) => <li key={index}><label>{index === 0 ? 'First choice' : `Next choice ${index + 1}`}<select aria-label={index === 0 ? 'First choice' : `Next choice ${index + 1}`} value={id} disabled={busy} onChange={event => change(targets.map((old, slot) => slot === index ? event.target.value : old))}><option value="">Choose a model</option>{models.filter(model => model.id === id || !targets.includes(model.id)).map(model => <option value={model.id} key={model.id}>{model.name} · {model.model_id}{model.base_url ? ` · ${model.base_url}` : ''}{(model.protocol || 'openai.chat.v1') !== route.profile.protocol ? ' (different protocol)' : ''}</option>)}</select></label><button className="quiet-button" disabled={busy || index === 0} aria-label={`Move choice ${index + 1} earlier`} onClick={() => { const next = [...targets]; [next[index-1], next[index]] = [next[index], next[index-1]]; change(next); }}>↑</button><button className="quiet-button" disabled={busy} aria-label={`Remove choice ${index + 1}`} onClick={() => change(targets.filter((_, slot) => slot !== index))}>Remove</button></li>)}</ol>
      {!targets.length && <p className="small-copy">No provider assigned. Save an empty route to keep this capability disconnected.</p>}
      <div className="target-actions"><button className="quiet-button" disabled={busy || targets.length >= 8 || targets.some(id => !id) || targets.length >= models.length} onClick={() => change([...targets, ''])}>Add provider choice</button><button className="primary-button" disabled={busy || !dirty || targets.some(id => !id)} onClick={async () => { setBusy(true); setError(''); try { await api(`/api/v1/capability-routes/${choice}`, mutation(identity, { revision, targets: targets.map((target_id, index) => ({ target_id, priority: 100-index })) }, 'PUT')); setDirty(false); await refresh(); setNotice(route.profile.executable ? 'Route saved. Only verified models will receive requests.' : 'Assignment saved as pending. This capability cannot dispatch yet.'); } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); } }}>Save assignment</button><button className="quiet-button" disabled={busy || dirty || !route.profile.executable || !targets.length || targets.some(id => { const model = models.find(item => item.id === id); return !model || !!model.active_run_id || (model.protocol || 'openai.chat.v1') !== route.profile.protocol; })} onClick={async () => { setBusy(true); setError(''); try { for (const id of targets) await verify(models.find(item => item.id === id)!, choice); await refresh(); setNotice('Provider checks finished. See the evidence below.'); } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); } }}>Verify assigned providers</button></div>
      {!dirty && route.targets.map(item => <p className="small-copy" key={item.target_id}><strong>{models.find(model => model.id === item.target_id)?.name}: {item.ready ? 'Ready' : 'Pending'}</strong> · {item.reason}</p>)}
    </>}{notice && <p className="success-message" role="status">{notice}</p>}{error && <p className="error-notice" role="alert">{error}</p>}
  </section>;
}

export const textChoices = [['auto', 'Automatic'], ['chat.general', 'Conversation'], ['reason.plan', 'Planning'], ['code.explain', 'Code explanation'], ['code.implement', 'Coding'], ['write.compose', 'Writing'], ['text.summarize', 'Summarization'], ['data.extract', 'Data extraction'], ['vision.describe', 'Vision']];
