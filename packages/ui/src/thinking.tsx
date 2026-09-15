import { useLayoutEffect, useRef, useState } from 'react';

export function Thinking({ text, streaming, stopped, truncated }: { text?: string; streaming: boolean; stopped: boolean; truncated?: boolean }) {
  const [open, setOpen] = useState(false);
  const viewport = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  useLayoutEffect(() => {
    if (open && follow.current && viewport.current) viewport.current.scrollTop = viewport.current.scrollHeight;
  }, [text, open]);
  if (!text) return null;
  return <details className="thinking-panel" open={open} onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>Thinking<span className="small-copy">{stopped ? ' · stopped' : streaming ? ' · streaming' : ''}</span></summary>
    <div className="thinking-text" ref={viewport} tabIndex={0} aria-label="Model thinking" onScroll={event => {
      const element = event.currentTarget;
      follow.current = element.scrollHeight - element.scrollTop - element.clientHeight < 48;
    }}>{text}</div>
    {truncated && <p className="small-copy">Only the first part of this thinking trace was kept.</p>}
    <p className="small-copy">From the model. Kept with this reply, separate from your memory.</p>
  </details>;
}
