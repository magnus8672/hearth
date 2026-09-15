import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { api, mutation, type Identity } from './api';

export type SideNote = { id: string; content: string; revision: number };

export function submitsOnEnter(event: KeyboardEvent<HTMLTextAreaElement>) {
  return event.key === 'Enter' && !event.shiftKey && !event.ctrlKey && !event.altKey && !event.metaKey && !event.nativeEvent.isComposing && event.keyCode !== 229;
}

export function SideNotes({ identity, running, disabled, onSend, onUse, onDirty }: {
  identity: Identity; running: boolean; disabled: boolean;
  onSend: (content: string, note?: SideNote) => Promise<boolean>;
  onUse: (content: string) => void; onDirty: (dirty: boolean) => void;
}) {
  const [items, setItems] = useState<SideNote[]>([]);
  const [content, setContent] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const pending = useRef<{ id: string; content: string } | null>(null);
  const saving = useRef(false);
  useEffect(() => { onDirty(!!content.trim()); return () => onDirty(false); }, [content, onDirty]);
  async function refresh() { setItems((await api<{ items: SideNote[] }>('/api/v1/side-notes')).items); }
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    async function poll() {
      try {
        const response = await api<{ items: SideNote[] }>('/api/v1/side-notes', { signal: controller.signal });
        if (!disposed) { setItems(response.items); timer = setTimeout(() => void poll(), 5000); }
      } catch (reason) { if (!disposed) setError((reason as Error).message); }
    }
    void poll();
    return () => { disposed = true; controller.abort(); clearTimeout(timer); };
  }, []);
  async function save() {
    if (!content.trim() || saving.current) return;
    saving.current = true; setBusy(true); setError('');
    try {
      if (pending.current?.content !== content) pending.current = { id: crypto.randomUUID(), content };
      await api('/api/v1/side-notes', mutation(identity, pending.current));
      setContent(''); pending.current = null; await refresh();
    } catch (reason) { setError((reason as Error).message); }
    finally { saving.current = false; setBusy(false); }
  }
  return <aside className="panel side-notes" aria-label="Private side notes"><div className="section-heading"><h2>For later</h2><span className="small-copy">Only you</span></div><p className="small-copy">Keep a thought here while your assistant works. Notes stay out of the conversation until you send them.</p>
    <form onSubmit={event => { event.preventDefault(); void save(); }}><label className="sr-only" htmlFor="side-note">New side note</label><textarea id="side-note" placeholder="Don’t forget to ask…" maxLength={4000} value={content} disabled={busy} onChange={event => setContent(event.target.value)} onKeyDown={event => { if (submitsOnEnter(event)) { event.preventDefault(); void save(); } }} /><div className="note-save-row"><span className="small-copy">Shift+Enter for a new line</span><button className="quiet-button" disabled={busy || !content.trim()}>Save note</button></div></form>
    <div className="note-list">{items.map(note => <article className="side-note" key={note.id}><button className="note-dismiss quiet-button" aria-label={`Dismiss note: ${note.content.slice(0, 40)}`} disabled={busy} onClick={async () => { setBusy(true); setError(''); try { await api(`/api/v1/side-notes/${note.id}/dismiss`, mutation(identity, { revision: note.revision })); await refresh(); } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); } }}>×</button><p>{note.content}</p><div className="note-actions"><button className="quiet-button" disabled={busy || disabled} onClick={async () => { if (await onSend(note.content, note)) await refresh().catch(reason => setError(reason.message)); }}>{running ? 'Steer with this' : 'Send to chat'}</button><button className="quiet-button" disabled={busy || disabled} onClick={() => onUse(note.content)}>Use in message</button></div></article>)}</div>
    {!items.length && <p className="small-copy">A little breathing room for your next idea.</p>}{error && <p className="error-notice" role="alert">{error}</p>}
  </aside>;
}
