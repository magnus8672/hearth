import { Children, useEffect, useId, useRef, useState, type CSSProperties, type ReactNode } from 'react';

type Layout = { left: number; right: number; hideLeft: boolean; hideRight: boolean; dock: 'side' | 'bottom' };
const defaults: Layout = { left: 280, right: 320, hideLeft: false, hideRight: false, dock: 'side' };
const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));

/** Local presentation preferences only. Collapsing a pane preserves its drafts. */
export function Workspace({ name, owner, leftLabel, rightLabel, conversation = false, children }: { name: string; owner: string; leftLabel: string; rightLabel?: string; conversation?: boolean; children: ReactNode }) {
  const key = `hearth.layout.${owner}.${name}`;
  const initial = { ...defaults, left: conversation ? 280 : 360 };
  const id = useId();
  const [layout, setLayout] = useState<Layout>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(key) || '{}');
      return { left: Number.isFinite(saved.left) ? clamp(saved.left, 200, 600) : initial.left, right: Number.isFinite(saved.right) ? clamp(saved.right, 240, 600) : defaults.right, hideLeft: saved.hideLeft === true, hideRight: saved.hideRight === true, dock: saved.dock === 'bottom' ? 'bottom' : 'side' };
    } catch { return initial; }
  });
  const root = useRef<HTMLDivElement>(null);
  const [left, center, right] = Children.toArray(children);
  useEffect(() => { try { localStorage.setItem(key, JSON.stringify(layout)); } catch { /* Storage is optional. */ } }, [key, layout]);
  useEffect(() => {
    const element = root.current!;
    const size = () => element.style.setProperty('--workspace-height', `${Math.max(520, window.innerHeight - element.getBoundingClientRect().top - window.scrollY - 24)}px`);
    size(); window.addEventListener('resize', size);
    const observer = new ResizeObserver(size); observer.observe(element.parentElement!);
    return () => { window.removeEventListener('resize', size); observer.disconnect(); };
  }, []);
  function separator(side: 'left' | 'right', label: string) {
    function setWidth(value: number) {
      const maximum = Math.max(240, Math.min(600, (root.current?.clientWidth || 1000) * .35));
      setLayout(previous => ({ ...previous, [side]: clamp(value, side === 'left' ? 200 : 240, maximum) }));
    }
    return <div className={`pane-resizer resize-${side}`} role="separator" aria-label={`Resize ${label}`} aria-orientation="vertical" aria-controls={`${id}-${side}`} aria-valuemin={side === 'left' ? 200 : 240} aria-valuemax={600} aria-valuenow={layout[side]} tabIndex={0}
      onDoubleClick={() => setWidth(initial[side])}
      onKeyDown={event => { if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) { event.preventDefault(); setWidth(event.key === 'Home' ? 200 : event.key === 'End' ? 600 : layout[side] + (event.key === 'ArrowRight' ? 20 : -20) * (side === 'right' ? -1 : 1)); } }}
      onPointerDown={event => { event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId); }}
      onPointerMove={event => { if (event.currentTarget.hasPointerCapture(event.pointerId)) { const box = root.current!.getBoundingClientRect(); setWidth(side === 'left' ? event.clientX - box.left : box.right - event.clientX); } }}
      onPointerUp={event => { if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }} />;
  }
  return <div className={`workspace ${conversation ? 'conversation-workspace' : 'media-workspace'}`}>
    <div className="workspace-tools" aria-label="Workspace layout">
      <button className="quiet-button" aria-expanded={!layout.hideLeft} aria-controls={`${id}-left`} onClick={() => setLayout(value => ({ ...value, hideLeft: !value.hideLeft }))}>{layout.hideLeft ? 'Show' : 'Hide'} {leftLabel}</button>
      {right && <><button className="quiet-button" aria-expanded={!layout.hideRight} aria-controls={`${id}-right`} onClick={() => setLayout(value => ({ ...value, hideRight: !value.hideRight }))}>{layout.hideRight ? 'Show' : 'Hide'} {rightLabel}</button><label>Dock {rightLabel}<select value={layout.dock} onChange={event => setLayout(value => ({ ...value, dock: event.target.value as Layout['dock'], hideRight: false }))}><option value="side">Right</option><option value="bottom">Below</option></select></label></>}
      <button className="quiet-button" onClick={() => setLayout(initial)}>Reset layout</button>
    </div>
    <div ref={root} className={`workspace-panes ${layout.hideLeft ? 'left-hidden' : ''} ${!right || layout.hideRight ? 'right-hidden' : ''} dock-${layout.dock}`} style={{ '--left-width': `${layout.left}px`, '--right-width': `${layout.right}px` } as CSSProperties}>
      <div id={`${id}-left`} className="workspace-left" hidden={layout.hideLeft}>{left}</div>
      {!layout.hideLeft && separator('left', leftLabel)}
      <div className="workspace-center">{center}</div>
      {right && !layout.hideRight && layout.dock === 'side' && separator('right', rightLabel!)}
      {right && <div id={`${id}-right`} className="workspace-right" hidden={layout.hideRight}>{right}</div>}
    </div>
  </div>;
}
