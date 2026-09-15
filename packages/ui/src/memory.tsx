import { useEffect, useState } from 'react';
import { api, mutation, type Identity } from './api';
import { Icon } from './index';

type Note = { id: string; title: string; body: string; kind: string; enabled: boolean; revision: number };
type Settings = { enabled: boolean; revision: number; generation: number; projected_generation: number; projected_at: string | null; projection_error: string | null };
type Overview = { settings: Settings; notes: Note[]; counts: { conversations: number; messages: number }; vault_projection: boolean };
type Source = { type: 'note' | 'message'; id: string; title: string; content?: string; body?: string; kind?: string; enabled?: boolean; revision: number; role?: string; model_id?: string; memory_excluded?: boolean; revisions?: { revision: number; content?: string; body?: string; origin: string }[] };
type History = { id: string; title: string; revision: number; archived: boolean; memory_excluded: boolean };

export type MemoryReceipt = { enabled: boolean; older_messages: number; search_status?: 'matched' | 'no_matches' | 'paused' | 'context_full'; sources: { type: string; id: string; revision: number; title: string }[] };

export function MemoryUsed({ receipt, unsaved = false }: { receipt?: MemoryReceipt; unsaved?: boolean }) {
  if (!receipt) return null;
  const status = { paused: 'Memory recall was paused for this reply.', no_matches: 'No matching memories were supplied for this reply.', context_full: 'Matching memories did not fit this reply’s context.' };
  return <div className="memory-used">{receipt.search_status && receipt.search_status !== 'matched' && <p className="small-copy">{status[receipt.search_status]}</p>}{receipt.sources?.length > 0 && <details><summary>Memory used · {receipt.sources.length} sources</summary><ul>{receipt.sources.map(source => <li key={source.id}><a onClick={event => { if (unsaved && !window.confirm('Leave your unsent message to open this memory source?')) event.preventDefault(); }} href={`#memory/${source.type}/${source.id}`}>{source.title}</a><span className="small-copy"> · revision {source.revision}</span></li>)}</ul></details>}{receipt.older_messages > 0 && <p className="small-copy">{receipt.older_messages} older messages are saved in your history. This reply used recent context and any memory sources shown above.</p>}</div>;
}

export function Memory({ identity, onDirty }: { identity: Identity; onDirty: (dirty: boolean) => void }) {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [source, setSource] = useState<Source | null>(null);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [kind, setKind] = useState('note');
  const [enabled, setEnabled] = useState(true);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Source[]>([]);
  const [history, setHistory] = useState<History[]>([]);
  const [offset, setOffset] = useState(0);
  const [historyChat, setHistoryChat] = useState('');
  const [messageOffset, setMessageOffset] = useState(0);
  const [historyMessages, setHistoryMessages] = useState<(Source & { sequence: number; status: string })[]>([]);
  const [importText, setImportText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const dirty = body !== (source?.body ?? source?.content ?? '') || (source?.type !== 'message' && (title !== (source?.title ?? '') || kind !== (source?.kind ?? 'note') || enabled !== (source?.enabled ?? true))) || !!importText;
  useEffect(() => { onDirty(dirty); const guard = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); }; window.addEventListener('beforeunload', guard); return () => { onDirty(false); window.removeEventListener('beforeunload', guard); }; }, [dirty, onDirty]);
  async function refresh() { setOverview(await api<Overview>('/api/v1/memory')); }
  async function browse() { setResults((await api<{ items: Source[] }>(`/api/v1/memory/search?q=${encodeURIComponent(query)}`)).items); }
  async function loadHistory(next = offset) { setHistory((await api<{ items: History[] }>(`/api/v1/memory/history?offset=${next}`)).items); setOffset(next); }
  async function browseChat(id: string, next = 0) { const value = await api<{ items: (Source & { sequence: number; status: string })[] }>(`/api/v1/memory/history/${id}/messages?offset=${next}`); setHistoryMessages(value.items); setHistoryChat(id); setMessageOffset(next); }
  function select(value: Source | null) { setSource(value); setTitle(value?.title ?? ''); setBody(value?.body ?? value?.content ?? ''); setKind(value?.kind ?? 'note'); setEnabled(value?.enabled ?? true); }
  async function open(type: string, id: string) {
    if (!['note', 'message'].includes(type) || !/^[0-9a-f-]{36}$/i.test(id)) return;
    const value = await api<Source>(`/api/v1/memory/${type === 'note' ? 'notes' : 'messages'}/${id}`);
    select({ ...value, type: type as Source['type'] });
  }
  function openSelected(type: string, id: string) {
    if (dirty && !window.confirm('Leave your unsaved memory edit?')) return;
    setImportText(''); setError(''); setNotice('');
    window.history.replaceState(null, '', `#memory/${type}/${id}`);
    void open(type, id).catch(reason => setError(reason.message));
  }
  useEffect(() => {
    void Promise.all([refresh(), browse(), loadHistory(0)]).catch(reason => setError(reason.message));
    const [, type, id] = window.location.hash.slice(1).split('/');
    if (type && id) void open(type, id).catch(reason => setError(reason.message));
    const timer = setInterval(() => void refresh().catch(() => {}), 10000);
    return () => clearInterval(timer);
  }, []);
  async function act(action: () => Promise<void>) { setBusy(true); setError(''); setNotice(''); try { await action(); } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); } }
  async function save() {
    await act(async () => {
      if (source?.type === 'message') await api(`/api/v1/memory/messages/${source.id}`, mutation(identity, { content: body, revision: source.revision }, 'PUT'));
      else {
        const value = await api<Note>(source ? `/api/v1/memory/notes/${source.id}` : '/api/v1/memory/notes', mutation(identity, { title, body, kind, enabled, ...(source ? { revision: source.revision } : {}) }, source ? 'PUT' : 'POST'));
        select({ ...value, type: 'note' });
      }
      if (source) await open(source.type, source.id);
      await refresh(); await browse(); setNotice('Saved. Your previous revision is preserved.');
    });
  }
  return <>
    <div className="info-banner"><Icon name="lock" /><p>Your private memory, in your words. Notes and past conversations can help future replies. You can correct them, pause recall, or take the full text history into Obsidian.</p></div>
    {error && <p className="error-notice" role="alert">{error}</p>}{notice && <p className="success-message" role="status">{notice}</p>}
    <section className="panel memory-controls"><div><h2>A place to remember.</h2><p className="small-copy">{overview?.counts.messages ?? '…'} messages in {overview?.counts.conversations ?? '…'} conversations, including archived chats.</p></div><label className="memory-check"><input type="checkbox" checked={overview?.settings.enabled ?? false} disabled={busy || !overview} onChange={event => { const value = event.currentTarget.checked; const revision = overview!.settings.revision; setOverview(current => current ? { ...current, settings: { ...current.settings, enabled: value } } : current); void act(async () => { try { await api('/api/v1/memory/settings', mutation(identity, { enabled: value, revision }, 'PUT')); } finally { await refresh(); } }); }} />Use memory across private chats</label><a className="quiet-button button-link" href="/api/v1/memory/vault.zip" download>Download Obsidian vault</a></section>
    <div className="memory-layout"><aside className="panel memory-list"><div className="section-heading"><h2>Your notes</h2><button className="quiet-button" disabled={busy} onClick={() => { if (!dirty || window.confirm('Leave your unsaved memory edit?')) { select(null); setImportText(''); window.history.replaceState(null, '', '#memory'); } }}>New note</button></div><p className="small-copy">Preferences are considered for every reply. Other notes are recalled when their words match your question.</p>{overview?.notes.map(note => <button className={`draft-item ${source?.id === note.id ? 'selected' : ''}`} key={note.id} onClick={() => openSelected('note', note.id)}><Icon name="writing" /><span>{note.title}<small>{note.kind}{note.enabled ? '' : ' · recall paused'}</small></span></button>)}{overview?.notes.length === 0 && <p className="small-copy">Keep a preference, project detail, or decision you want to carry between chats.</p>}</aside>
      <section className="panel memory-editor"><h2>{source?.type === 'message' ? 'Correct your history' : source ? 'Edit a memory' : 'Keep something in mind'}</h2>{source?.type === 'message' ? <p className="small-copy">{source.title} · {source.role === 'user' ? 'You' : `hearth${source.model_id ? ' · ' + source.model_id : ''}`} · revision {source.revision}. A correction preserves the original text and is marked in the chat.</p> : <><label>Title<input maxLength={200} value={title} disabled={busy} onChange={event => setTitle(event.target.value)} /></label><label>Kind<select value={kind} disabled={busy} onChange={event => setKind(event.target.value)}><option value="note">Note</option><option value="preference">Preference</option><option value="decision">Decision</option></select></label></>}
        <label>{source?.type === 'message' ? 'Message text' : 'Memory text'}<textarea aria-label={source?.type === 'message' ? 'Message text' : 'Memory text'} rows={10} maxLength={source?.type === 'message' ? 65000 : 6000} value={body} disabled={busy} onChange={event => setBody(event.target.value)} placeholder="For example: My project workshop uses Python and runs on my home server." /></label>{source?.type !== 'message' && <label className="memory-check"><input type="checkbox" checked={enabled} disabled={busy} onChange={event => setEnabled(event.target.checked)} />Allow this note in future replies</label>}
        <div className="target-actions"><button className="primary-button" disabled={busy || !body.trim() || (source?.type !== 'message' && !title.trim()) || !dirty || !!importText} onClick={() => void save()}>Save {source?.type === 'message' ? 'correction' : 'memory'}</button>{source && <button className="quiet-button" disabled={busy} onClick={() => { if (!dirty || window.confirm('Discard this unsaved edit?')) { setImportText(''); void open(source.type, source.id).catch(reason => setError(reason.message)); } }}>Reload source</button>}{source?.type === 'note' && <button className="quiet-button" disabled={busy} onClick={() => { if (window.confirm('Remove this note from memory? Its revision history will remain in your private archive.')) void act(async () => { await api(`/api/v1/memory/notes/${source.id}/remove`, mutation(identity, { revision: source.revision })); select(null); await refresh(); await browse(); setNotice('Removed from recall. Revision history stays in your private archive.'); }); }}>Remove note</button>}</div>
        {source?.revisions && <details className="memory-revisions"><summary>Previous revisions</summary>{source.revisions.map(item => <article key={item.revision}><strong>Revision {item.revision} · {item.origin}</strong><pre>{item.body ?? item.content}</pre></article>)}</details>}
      </section></div>
    <section className="panel memory-history"><h2>Find a thought</h2><form className="memory-search" onSubmit={event => { event.preventDefault(); void act(browse); }}><label>Search notes and chat history<input maxLength={200} value={query} onChange={event => setQuery(event.target.value)} placeholder="A project name, a decision, a detail…" /></label><button className="quiet-button" disabled={busy}>Search</button></form><p className="small-copy">Search uses matching words. Excluded conversations remain searchable here for you, but are not recalled in other chats.</p><div className="memory-results">{results.map(item => <button key={item.id} className="memory-result" onClick={() => openSelected(item.type, item.id)}><strong>{item.title}</strong><span className="small-copy">{item.type} · revision {item.revision}{item.enabled ? '' : ' · excluded from recall'}</span><span>{(item.content ?? item.body ?? '').slice(0, 280)}</span></button>)}</div>{results.length === 0 && <p>No matching sources yet.</p>}</section>
    <section className="panel memory-history"><h2>Your conversation archive</h2><p className="small-copy">Exclusion affects recall across chats. It does not erase history or remove a message from its own active conversation.</p>{history.map(item => <div className="memory-history-row" key={item.id}><div><strong>{item.title}</strong><span className="small-copy">{item.archived ? 'Archived' : 'Active'} · {item.memory_excluded ? 'Excluded from recall' : 'Available for recall'}</span></div><button className="quiet-button" disabled={busy} onClick={() => void act(() => browseChat(item.id))}>View messages</button><button className="quiet-button" disabled={busy} onClick={() => void act(async () => { await api(`/api/v1/memory/history/${item.id}`, mutation(identity, { revision: item.revision, enabled: item.memory_excluded }, 'PUT')); await loadHistory(); await refresh(); })}>{item.memory_excluded ? 'Allow recall' : 'Exclude from recall'}</button></div>)}<div className="target-actions"><button className="quiet-button" disabled={busy || offset === 0} onClick={() => void act(() => loadHistory(Math.max(0, offset-100)))}>Previous</button><button className="quiet-button" disabled={busy || history.length < 100} onClick={() => void act(() => loadHistory(offset+100))}>More conversations</button></div>{historyChat && <div className="memory-results" aria-label="Saved conversation history">{historyMessages.map(item => <button className="memory-result" key={item.id} onClick={() => openSelected('message', item.id)}><strong>{item.sequence} · {item.role === 'user' ? 'You' : 'hearth'}</strong><span className="small-copy">{item.status} · revision {item.revision}</span><span>{item.content}</span></button>)}<div className="target-actions"><button className="quiet-button" disabled={busy || messageOffset === 0} onClick={() => void act(() => browseChat(historyChat, Math.max(0, messageOffset-50)))}>Earlier messages</button><button className="quiet-button" disabled={busy || historyMessages.length < 50} onClick={() => void act(() => browseChat(historyChat, messageOffset+50))}>Later messages</button></div></div>}</section>
    <section className="panel memory-import"><h2>Make yourself at home in Obsidian.</h2><p>Download your vault, extract it into a new folder, and open that folder in Obsidian. Edit a file in <code>notes/</code> or <code>messages/</code>, then bring it back here. Links between notes appear in Obsidian’s graph.</p><p className="small-copy">Desktop edits are imported explicitly in this build. Generated transcripts and JSONL preserve the full text history. Image and audio binaries are not included in this text export.</p><label>Import edited Markdown<input type="file" accept=".md,text/markdown,text/plain" disabled={busy || (dirty && !importText)} onChange={event => { const file = event.target.files?.[0]; if (!file) return; if (file.size > 1000000) { setError('Choose a Markdown file smaller than 1 MB.'); return; } void file.text().then(setImportText).catch(() => setError('This file could not be read.')); event.target.value = ''; }} /></label>{importText && <><label>Review the file before importing<textarea aria-label="Review the file before importing" rows={12} value={importText} onChange={event => setImportText(event.target.value)} /></label><div className="target-actions"><button className="primary-button" disabled={busy} onClick={() => void act(async () => { const result = await api<{ type: string; source: Source }>('/api/v1/memory/import', mutation(identity, { markdown: importText })); setImportText(''); await open(result.type, result.source.id); await refresh(); await browse(); setNotice('Imported as a new revision.'); })}>Apply Markdown edit</button><button className="quiet-button" disabled={busy} onClick={() => setImportText('')}>Dismiss import</button></div></>}
      {overview?.vault_projection && <p className="small-copy" role="status">{overview.settings.projection_error || (overview.settings.projected_generation >= overview.settings.generation ? 'Server vault is up to date.' : 'Updating your server vault. Your history is already saved in the database.')}</p>}
    </section>
  </>;
}
