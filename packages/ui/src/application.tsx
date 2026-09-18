import { useEffect, useState } from 'react';
import { api, type Identity } from './api';
import { Chat } from './chat';
import { Accounts } from './accounts';
import { Channels } from './channels';
import { Images } from './images';
import { Geometry } from './geometry';
import { Memory } from './memory';
import { ClientConnections } from './client-connections';
import { HeadSettings } from './head-settings';
import { ToolsAdmin, MyTools } from './tools';
import { Providers } from './providers';
import { Workers } from './workers';
import { Brand, Icon, Status, ThemeControl, useControlConnection } from './index';

type Audience = 'admin' | 'user';
type Capability = { builtin?: boolean; executable?: boolean; capability_id: string; display_name: string; description: string; icon: string; state: 'unassigned' | 'ready' | 'offline'; input_modalities: string[]; output_modalities: string[]; reason: string };
type Draft = { id: string; title: string; revision: number; content?: string };
type Workspace = { workspace: { name: string; locality: string }; drafts: Draft[] };
type Farm = { farm: { name: string }; members: { id: string; display_name: string; roles: string[]; state: string }[] };

export function Application({ audience }: { audience: Audience }) {
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    fetch('/api/v1/session', { credentials: 'same-origin', cache: 'no-store' }).then(async response => {
      if (response.ok) setIdentity(await response.json() as Identity);
      else if (response.status !== 401) setError((await response.json()).error?.message || 'Account connection unavailable.');
    }).catch(() => setError('hearth is not reachable. Start the appliance and try again.')).finally(() => setLoaded(true));
  }, []);
  async function logout() {
    if (!identity) return;
    try {
      const response = await fetch('/api/v1/logout', { method: 'POST', headers: { 'X-Hearth-CSRF': identity.csrf_token } });
      if (!response.ok) throw new Error('Sign-out could not complete. Please try again.');
      window.location.assign('/');
    } catch (reason) { setError((reason as Error).message); }
  }
  return <div className="entry-shell">
    <a className="skip-link" href="#main">Skip to content</a>
    <header className="app-header"><a className="home-link" href="/" aria-label="hearth home"><Brand /></a><span className="app-kind">{audience === 'admin' ? 'Administration' : 'Your workspace'}</span><ThemeControl />
      {identity && <button className="quiet-button" onClick={() => void logout()}>Sign out</button>}
    </header>
    {error && <p className="global-notice error-notice" role="alert">{error}</p>}
    {!loaded ? <main id="main" className="loading-page"><Status state="warming">Opening your hearth…</Status></main> : identity ? <Dashboard audience={audience} identity={identity} /> : <Welcome audience={audience} />}
    <footer className="app-footer"><span>hearth <span className="footer-dot">·</span> Agentic Cloud at Home</span><span>Local test build <span className="footer-dot">·</span> Local models & private conversations</span></footer>
  </div>;
}

function Welcome({ audience }: { audience: Audience }) {
  const { state, retry } = useControlConnection();
  const [ownerCreated, setOwnerCreated] = useState(false);
  useEffect(() => { api<{ owner_created: boolean }>('/api/v1/setup').then(value => setOwnerCreated(value.owner_created)).catch(() => {}); }, [state]);
  const admin = audience === 'admin';
  return <main id="main" className="entry-main">
    <div className="welcome-copy"><p className="eyebrow"><Icon name="hearth" /> AGENTIC CLOUD AT HOME</p><h1>{admin ? <>Make yourself<br />at home.</> : <>A place for<br />your ideas.</>}</h1><p className="lead">{admin ? 'Bring your machines together. Keep your intelligence close.' : 'A private place to gather your thoughts, ready for what comes next.'}</p><div className="principles"><div><Icon name="lock" />Private by default</div><div><Icon name="nodes" />Your machines, working together</div><div><Icon name="settings" />You stay in control</div></div></div>
    <section className="entry-card" aria-labelledby="entry-title"><div className="card-mark"><Icon name={admin ? 'hearth' : 'writing'} /></div><p className="eyebrow">WELCOME HOME</p><h2 id="entry-title">{ownerCreated ? 'Your hearth is here.' : 'Let’s light the first spark.'}</h2><p>{ownerCreated ? 'Sign in with your hearth account. Your password and authenticator stay with the local identity service.' : 'Open the local hearth setup tool to create the Owner account and prepare browser trust.'}</p>
      <div className="connection-panel" aria-live="polite"><div className="connection-label">Control plane</div><Status state={state === 'ready' ? 'ready' : state === 'checking' ? 'warming' : 'offline'}>{state === 'ready' ? 'Database connected' : state === 'checking' ? 'Checking connection' : 'Connection unavailable'}</Status><p>{state === 'ready' ? 'Local service connected. Sign in to see your available capabilities.' : 'Checking the local service and its database.'}</p></div>
      {ownerCreated && state === 'ready' ? <a className="primary-button button-link" href="/auth/login"><Icon name="lock" />Sign in to {admin ? 'Administration' : 'your workspace'}</a> : <button className="primary-button" disabled={state === 'checking'} onClick={retry}>Check connection</button>}
      {ownerCreated && !admin && <p className="small-copy"><a href="/auth/register">Create an account</a>. Set up your password and authenticator, then wait for an administrator to grant access.</p>}
    </section>
    <section className="capability-intro" aria-label="What you can try"><div><Icon name="security" /><h3>Accounts that belong to you</h3><p>One sign-in for your workspace and permitted administration, protected by an authenticator and recovery codes.</p></div><div><Icon name="writing" /><h3>Keep a thought for later</h3><p>Create and edit private drafts. Your work stays on this hearth when you close the browser.</p></div><div><Icon name="cube" /><h3>See what comes next</h3><p>Explore the capability catalog. Chat becomes available after a local model server passes verification.</p></div></section>
  </main>;
}

function Dashboard({ audience, identity }: { audience: Audience; identity: Identity }) {
  const admin = audience === 'admin';
  const allowed = identity.permissions.includes('farm.inspect');
  const userPermissions: Record<string, string> = { chat: 'conversation.own', channels: 'channel.use', images: 'capability.image.generate', geometry: 'capability.geometry.generate', memory: 'capability.memory.retrieve', drafts: 'draft.use', tools: 'tool.use', clients: 'api_key.own' };
  const waiting = identity.state === 'pending' || (!admin && !identity.permissions.length);
  const canOpen = (page: string) => page === 'capabilities' ? !waiting : identity.permissions.includes(userPermissions[page]);
  const firstPage = Object.keys(userPermissions).find(canOpen) || 'capabilities';
  const adminRoute = () => { const [page, capability = ''] = window.location.hash.slice(1).split('/'); return { page: ['overview', 'providers', 'workers', 'capabilities', 'tools', 'people', 'settings'].includes(page) ? page : 'overview', capability }; };
  const userRoute = () => ['chat', 'channels', 'images', 'geometry', 'drafts', 'memory', 'capabilities', 'tools', 'clients'].includes(window.location.hash.slice(1).split('/')[0]) ? window.location.hash.slice(1).split('/')[0] : firstPage;
  const [requestedTab, setTab] = useState(admin ? adminRoute().page : userRoute());
  const tab = admin || canOpen(requestedTab) ? requestedTab : firstPage;
  const [providerCapability, setProviderCapability] = useState(admin ? adminRoute().capability : '');
  function navigate(page: string, capability = '') { setTab(page); setProviderCapability(capability); window.history.pushState(null, '', `#${page}${capability ? '/' + capability : ''}`); }
  useEffect(() => { const restore = () => { const route = adminRoute(); setTab(admin ? route.page : userRoute()); setProviderCapability(admin ? route.capability : ''); }; window.addEventListener('popstate', restore); window.addEventListener('hashchange', restore); return () => { window.removeEventListener('popstate', restore); window.removeEventListener('hashchange', restore); }; }, [admin]);
  const [capabilities, setCapabilities] = useState<Capability[]>([]);
  const [farm, setFarm] = useState<Farm | null>(null);
  const [draftDirty, setDraftDirty] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    if (waiting || (admin && !allowed)) return;
    api<{ items: Capability[] }>('/api/v1/capabilities').then(value => setCapabilities(value.items)).catch(reason => setError(reason.message));
    if (admin) api<Farm>('/api/v1/farm').then(setFarm).catch(reason => setError(reason.message));
  }, [admin, allowed, tab, waiting]);
  if (waiting) return <main id="main" className="loading-page"><section className="entry-card"><Icon name="lock" /><h1 className="page-title">Welcome home, {identity.display_name}.</h1><h2>Waiting for access</h2><p>Your account is ready. An administrator needs to approve your access before you can chat, generate images or use other capabilities.</p><p>Your workspace stays here while you wait.</p><a className="primary-button button-link" href="/auth/login">Check access</a></section></main>;
  if (admin && !allowed) return <main id="main" className="loading-page"><div className="entry-card"><Icon name="lock" /><h1 className="page-title">Your workspace is ready.</h1><p>Administration requires a farm role granted by an administrator.</p><a className="primary-button button-link" href={identity.user_origin}>Open your workspace</a></div></main>;
  return <div className="dashboard-layout"><aside className="sidebar"><div className="farm-label"><span className="farm-avatar"><Icon name="hearth" /></span><div><strong>{farm?.farm.name || 'Your hearth'}</strong><span>Local · private by default</span></div></div>
    <nav aria-label={admin ? 'Administration' : 'Workspace'}>{(admin ? [['overview', 'activity', 'Overview'], ['providers', 'nodes', 'Providers'], ['workers', 'nodes', 'Workers'], ['capabilities', 'cube', 'Capabilities'], ['tools', 'settings', 'Shared tools'], ['people', 'users', 'People'], ['settings', 'settings', 'Settings']] : [['chat', 'hearth', 'Private chat'], ['channels', 'users', 'Channels'], ['images', 'image', 'Images'], ['geometry', 'cube', '3D models'], ['memory', 'writing', 'Memory'], ['drafts', 'writing', 'Private drafts'], ['tools', 'settings', 'Tools'], ['clients', 'nodes', 'Client connections'], ['capabilities', 'cube', 'Capabilities']]).filter(([id]) => admin || canOpen(id)).map(([id, icon, label]) => <button key={id} className={`nav-item ${tab === id ? 'selected' : ''}`} aria-current={tab === id ? 'page' : undefined} onClick={() => { if (tab === id || !draftDirty || window.confirm('Leave your unsaved writing?')) navigate(id); }}><Icon name={icon} />{label}</button>)}</nav>
    <div className="sidebar-bottom"><div className="privacy-label"><Icon name="lock" /><span>Cloud budget<br /><strong>$0 · Local only</strong></span></div>{(admin || allowed) && <a className="nav-item" href={`${admin ? identity.user_origin : identity.admin_origin}/auth/login`}><Icon name={admin ? 'writing' : 'settings'} />{admin ? 'Your workspace' : 'Administration'}<span aria-hidden="true">↗</span></a>}</div>
  </aside><main id="main" className="dashboard-main"><div className="page-heading"><div><p className="eyebrow">{admin ? <>YOUR <span className="brand-name">hearth</span></> : 'JUST FOR YOU'}</p><h1 className="page-title">{tab === 'workers' ? 'Your machines, working together.' : tab === 'settings' ? 'Make yourself at home.' : tab === 'tools' ? 'Tools that work together.' : tab === 'clients' ? 'Bring your own agent.' : tab === 'overview' ? `Welcome home, ${identity.display_name}.` : tab === 'capabilities' ? 'Room for possibility.' : tab === 'people' ? 'The people at home.' : tab === 'providers' ? 'Your models, at home.' : tab === 'memory' ? 'Keep what matters.' : tab === 'geometry' ? 'A new dimension.' : tab === 'images' ? 'Make room for imagination.' : tab === 'channels' ? 'Better together.' : tab === 'chat' ? 'Let’s think together.' : 'Keep the spark.'}</h1><p className="muted">{tab === 'workers' ? 'Service control and a queue for each GPU.' : tab === 'settings' ? 'Your address, certificates and connections.' : tab === 'tools' ? 'One shared gateway, available across your farm.' : tab === 'clients' ? 'Your local tools, powered by your hearth.' : tab === 'overview' ? 'A clear view of your farm, from the first connection onward.' : tab === 'capabilities' ? 'Choose what you want to do. hearth will bring the right machines together.' : tab === 'people' ? 'Farm roles govern administration. Personal content remains private.' : tab === 'providers' ? 'Connect the services you already run and give each capability a home.' : tab === 'memory' ? 'Editable memories and your complete conversation history, ready for Obsidian.' : tab === 'geometry' ? 'Turn a picture into a model, on your own machines.' : tab === 'images' ? 'Pictures made on your machines, saved just for you.' : tab === 'channels' ? 'A shared conversation for your people and your local assistant.' : tab === 'chat' ? 'A conversation with your local model, saved in your personal workspace.' : 'A quiet space for thoughts, plans, and the beginning of something.'}</p></div><span className="identity-chip">{identity.roles[0] || 'Awaiting approval'}<span className="avatar">{identity.display_name.slice(0, 1).toUpperCase()}</span></span></div>
    {error && <p className="error-notice" role="alert">{error}</p>}
    {tab === 'overview' && <><div className="stats-grid"><div className="stat-card"><span>Control plane</span><strong className="stat-word">Connected</strong><Status state="ready">Database & identity verified</Status></div><div className="stat-card"><span>Verified capabilities</span><strong>{capabilities.filter(item => item.state === 'ready').length} / {capabilities.length}</strong><span>Readiness follows real provider probes</span></div><div className="stat-card"><span>People</span><strong>{farm?.members.length ?? '…'}</strong><span>Private personal workspaces</span></div></div><section className="provider-card"><div className="card-mark"><Icon name="hearth" /></div><div><p className="eyebrow">BRING WHAT YOU ALREADY RUN</p><h2>Give your hearth a voice.</h2><p>Connect LM Studio or another compatible local server. Verify its model, then open your workspace for a private conversation.</p></div><button className="primary-button" onClick={() => navigate('providers')}>Open Providers</button></section><p className="subtle-note"><Icon name="lock" />Existing servers stay under your control. Cloud spending remains disabled.</p></>}
    {tab === 'providers' && <Providers key={capabilities.find(item => item.capability_id === providerCapability)?.capability_id || ''} identity={identity} capability={capabilities.find(item => item.capability_id === providerCapability)} onClear={() => navigate('providers')} />}
    {tab === 'capabilities' && <><div className="info-banner"><Icon name="activity" /><p>Each capability needs its own verification. A successful chat probe does not enable tools, images, or the administration agent.</p></div><section className="panel"><h2>Shared tools</h2><p>One MCP gateway for all tool-capable models. Register and approve tools once for the farm.</p><button className="quiet-button" onClick={() => navigate('tools')}>{admin ? 'Configure shared tools' : 'Open your tools'}</button></section><div className="catalog-grid">{capabilities.map(item => <article className="capability-card" key={item.capability_id}><div className="capability-top"><span className="card-mark"><Icon name={item.icon} /></span><Status state={item.state}>{item.state === 'ready' ? 'Verified' : item.executable === false ? 'Adapter pending' : item.state === 'offline' ? 'Needs verification' : 'Unassigned'}</Status></div><h2>{item.display_name}</h2><p>{item.description}</p><p className="small-copy">{item.reason}</p><div className="modality-line">{item.input_modalities.join(' + ')} <span aria-hidden="true">→</span> {item.output_modalities.join(' + ')}</div>{item.builtin ? <a className="quiet-button button-link" href={`${identity.user_origin}/#memory`}>Open your memory</a> : admin && <button className="quiet-button capability-action" onClick={() => navigate('providers', item.capability_id)}>{item.executable === false ? 'Configure assignment' : item.state === 'offline' ? 'Verify provider' : item.state === 'ready' ? 'Configure provider' : 'Configure'}</button>}</article>)}</div></>}
    {tab === 'tools' && (admin ? <ToolsAdmin identity={identity} /> : <MyTools identity={identity} />)}
    {tab === 'workers' && admin && <Workers identity={identity} />}
    {tab === 'settings' && admin && <HeadSettings identity={identity} />}
    {tab === 'clients' && !admin && <ClientConnections identity={identity} />}
    {tab === 'memory' && !admin && <Memory identity={identity} onDirty={setDraftDirty} />}
    {tab === 'geometry' && <Geometry identity={identity} onDirty={setDraftDirty} />}
    {tab === 'images' && <Images identity={identity} onDirty={setDraftDirty} />}
    {tab === 'channels' && <Channels identity={identity} onDirty={setDraftDirty} />}
    {tab === 'chat' && <Chat identity={identity} onDirty={setDraftDirty} />}
    {tab === 'people' && <Accounts identity={identity} />}
    {tab === 'drafts' && <Drafts identity={identity} onDirty={setDraftDirty} />}
  </main></div>;
}

function Drafts({ identity, onDirty }: { identity: Identity; onDirty: (dirty: boolean) => void }) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [selected, setSelected] = useState<Draft | null>(null);
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const dirty = title !== (selected?.title || '') || content !== (selected?.content || '');
  useEffect(() => { onDirty(dirty); return () => onDirty(false); }, [dirty, onDirty]);
  async function refresh() { setWorkspace(await api<Workspace>('/api/v1/workspace')); }
  useEffect(() => { void refresh().catch(reason => setError(reason.message)); }, []);
  useEffect(() => {
    const beforeUnload = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); };
    window.addEventListener('beforeunload', beforeUnload);
    return () => window.removeEventListener('beforeunload', beforeUnload);
  }, [dirty]);
  async function open(item: Draft | null) {
    if (dirty && !window.confirm('Leave this draft without saving your changes?')) return;
    setError(''); setMessage(''); setBusy(true);
    try {
      const draft = item ? await api<Draft>(`/api/v1/drafts/${item.id}`) : null;
      setSelected(draft); setTitle(draft?.title || ''); setContent(draft?.content || '');
    } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); }
  }
  async function save() {
    setError(''); setMessage(''); setBusy(true);
    try {
      const draft = await api<Draft>(selected ? `/api/v1/drafts/${selected.id}` : '/api/v1/drafts', { method: selected ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json', 'X-Hearth-CSRF': identity.csrf_token }, body: JSON.stringify({ title, content, ...(selected ? { revision: selected.revision } : {}) }) });
      setSelected(draft); setTitle(draft.title); setContent(draft.content || ''); await refresh(); setMessage('Saved to your private workspace.');
    } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); }
  }
  async function archive() {
    if (!selected || !window.confirm('Archive this draft? It will be removed from your active list.')) return;
    setBusy(true); setError('');
    try {
      await api(`/api/v1/drafts/${selected.id}`, { method: 'DELETE', headers: { 'X-Hearth-CSRF': identity.csrf_token } });
      setSelected(null); setTitle(''); setContent(''); await refresh(); setMessage('Draft archived.');
    } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); }
  }
  return <><div className="draft-layout"><section className="draft-list panel" aria-label="Saved drafts"><div className="section-heading"><h2>Your drafts</h2><button className="quiet-button" onClick={() => void open(null)} disabled={busy}>+ New</button></div><p className="small-copy">{workspace ? `${workspace.drafts.length} saved · Personal workspace` : 'Opening workspace…'}</p>{workspace?.drafts.length === 0 && <div className="empty-drafts"><Icon name="writing" /><h3>Every idea starts somewhere.</h3><p>Write your first thought. Save it here and come back whenever you’re ready.</p></div>}{workspace?.drafts.map(item => <button className={`draft-item ${selected?.id === item.id ? 'selected' : ''}`} disabled={busy} onClick={() => void open(item)} key={item.id}><Icon name="writing" /><span>{item.title}</span></button>)}</section>
      <section className="editor panel" aria-label="Draft editor"><div className="section-heading"><span className="privacy-label"><Icon name="lock" />Only you</span><span className="small-copy">{dirty ? 'Unsaved changes' : selected ? 'Saved locally' : 'New draft'}</span></div><label className="sr-only" htmlFor="draft-title">Draft title</label><input id="draft-title" className="draft-title" maxLength={200} value={title} onChange={event => setTitle(event.target.value)} placeholder="Give your idea a name" disabled={busy} /><label className="sr-only" htmlFor="draft-content">Your draft</label><textarea id="draft-content" value={content} onChange={event => setContent(event.target.value)} placeholder="What’s on your mind?" maxLength={32000} disabled={busy} /><div className="editor-actions"><span className="small-copy">{content.length.toLocaleString()} / 32,000</span>{selected && <button className="quiet-button" onClick={() => void archive()} disabled={busy}>Archive</button>}<button className="primary-button" disabled={busy || !title.trim() || !content.trim() || !dirty} onClick={() => void save()}>{busy ? 'Saving…' : 'Save draft'}</button></div><div aria-live="polite">{message && <p className="success-message">{message}</p>}{error && <p className="error-notice" role="alert">{error}</p>}</div></section></div><p className="subtle-note"><Icon name="hearth" />Your drafts are saved without being sent to a model. Open Private chat when you want an assistant’s reply.</p></>;
}
