import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from './api';
import { Icon } from './index';
import './farm-map.css';

type Node = { id: string; name: string; capability: string; icon: string; residency: string; verified: boolean; model?: string; endpoint?: string; pool?: string; provider?: string; priority?: number; observed_at?: string | null; verified_at?: string | null; target_state?: string };
type Pool = { id: string; name: string; state: string; queued: number; policy: string; desired_service: string | null; ready_service: string | null };
type Machine = { id: string; name: string; address: string; kind: string; nodes: Node[]; pools: Pool[] };
type Snapshot = { observed_at: string; machines: Machine[]; binding_count: number; unassigned: { id: string; name: string; icon: string }[]; unbound_targets: { target_id: string; provider: string; model: string; machine: string; residency: string }[] };
const labels: Record<string, string> = { builtin: 'Built-in', loaded: 'Loaded', unloaded: 'Not loaded', service_ready: 'Service ready', on_demand: 'On demand', offline: 'Worker offline', paused: 'Paused', failed: 'Service failed', starting: 'Starting', unknown: 'Residency unknown' };
const date = (value?: string | null) => value ? new Date(value).toLocaleString() : 'Not observed';

export function FarmMap() {
  const [data, setData] = useState<Snapshot | null>(null);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState('head');
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [showModels, setShowModels] = useState(true);
  const [showUnassigned, setShowUnassigned] = useState(false);
  const viewport = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 900, height: 700 });
  const [view, setView] = useState<{ scale: number; x: number; y: number } | null>(null);
  const drag = useRef<{ x: number; y: number; tx: number; ty: number; scale: number } | null>(null);
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    let controller: AbortController | undefined;
    let running = false;
    const load = async () => {
      if (stopped || running) return;
      clearTimeout(timer);
      if (document.hidden) { timer = setTimeout(() => void load(), 10000); return; }
      running = true; controller = new AbortController(); setLoading(true);
      const timeout = setTimeout(() => controller?.abort(), 20000);
      try {
        const value = await api<Snapshot>('/api/v1/farm-map', { signal: controller.signal });
        if (!stopped) { setData(value); setError(''); }
      } catch { if (!stopped) setError('Farm map updates are unavailable. Displayed observations are stale; retry to check the farm.'); }
      finally { clearTimeout(timeout); running = false; if (!stopped) { setLoading(false); timer = setTimeout(() => void load(), 10000); } }
    };
    const visible = () => { if (!document.hidden) void load(); };
    void load(); document.addEventListener('visibilitychange', visible);
    return () => { stopped = true; clearTimeout(timer); controller?.abort(); document.removeEventListener('visibilitychange', visible); };
  }, [refresh]);
  useEffect(() => {
    if (!viewport.current) return;
    const observer = new ResizeObserver(([entry]) => setSize({ width: entry.contentRect.width, height: entry.contentRect.height }));
    observer.observe(viewport.current); return () => observer.disconnect();
  }, [!!data]);
  const layout = useMemo(() => {
    const machines = data?.machines || [];
    const hosts = machines.filter(m => m.id !== 'head');
    const width = hosts.length > 1 ? 1440 : 760;
    const head = machines.find(m => m.id === 'head');
    const headHeight = 220 + Math.ceil((head?.nodes.length || 0) / 3) * 145;
    const boxes: { machine: Machine; x: number; y: number; w: number; h: number }[] = [];
    if (head) boxes.push({ machine: head, x: width / 2 - 330, y: 20, w: 660, h: headHeight });
    let y = headHeight + 130;
    for (let i = 0; i < hosts.length; i += 2) {
      const row = hosts.slice(i, i + 2);
      const heights = row.map(m => collapsed.has(m.id) ? 135 : 175 + Math.max(1, Math.ceil(m.nodes.length / 3)) * 160);
      row.forEach((machine, j) => boxes.push({ machine, x: row.length === 1 ? width / 2 - 330 : 30 + j * 720, y, w: 660, h: heights[j] }));
      y += Math.max(...heights) + 110;
    }
    return { width, height: hosts.length ? y - 65 : headHeight + 85, boxes };
  }, [data, collapsed]);
  const fit = Math.min((size.width - 24) / layout.width, (size.height - 65) / layout.height, 1.2);
  const camera = view || { scale: fit, x: (size.width - layout.width * fit) / 2, y: 14 };
  const allNodes = data?.machines.flatMap(m => m.nodes.map(n => ({ ...n, machine: m }))) || [];
  const node = allNodes.find(n => n.id === selected);
  const unassigned = data?.unassigned.find(n => n.id === selected);
  const selectionMissing = selected !== 'head' && !node && !unassigned;
  useEffect(() => { if (selectionMissing) setSelected('head'); }, [selectionMissing]);
  function zoom(factor: number) {
    const scale = Math.max(.15, Math.min(2, camera.scale * factor));
    setView({ scale, x: size.width / 2 - (size.width / 2 - camera.x) * scale / camera.scale, y: size.height / 2 - (size.height / 2 - camera.y) * scale / camera.scale });
  }
  function toggle(machine: Machine) {
    setCollapsed(previous => { const next = new Set(previous); if (next.has(machine.id)) next.delete(machine.id); else next.add(machine.id); return next; });
    if (node?.machine.id === machine.id) setSelected('head');
  }
  const position = (index: number, count: number, head: boolean) => ({ x: 330 + ((index % 3) - (Math.min(3, count - Math.floor(index / 3) * 3) - 1) / 2) * 205, y: (head ? 207 : 147) + Math.floor(index / 3) * 160 });
  return <section className="farm-map" aria-label="Farm map">
    {error && <p className="error-notice" role="alert">{error}</p>}
    <div className="fm-toolbar"><div><strong>Topology</strong><span className="small-copy">{data ? `${data.machines.length} host groups · ${data.binding_count} bindings` : 'Reading farm configuration…'}</span></div><div><label><input type="checkbox" checked={showModels} onChange={e => setShowModels(e.target.checked)} />Model labels</label><button className="quiet-button" aria-expanded={showUnassigned} onClick={() => setShowUnassigned(!showUnassigned)}>Unassigned {data?.unassigned.length ?? 0}</button><button className="quiet-button" disabled={loading} onClick={() => setRefresh(v => v + 1)}>{loading ? 'Updating…' : 'Refresh'}</button></div></div>
    {!data ? <p className="fm-empty">{error ? 'The farm map could not be loaded.' : 'Checking capability bindings and residency…'}</p> : <div className="fm-body"><div className="fm-map-shell"><div ref={viewport} className="fm-viewport" aria-label="Capability tree. Drag the background to pan, or use the zoom controls." onPointerDown={e => { if ((e.target as Element).closest('button') || e.button !== 0) return; drag.current = { x: e.clientX, y: e.clientY, tx: camera.x, ty: camera.y, scale: camera.scale }; e.currentTarget.setPointerCapture(e.pointerId); }} onPointerMove={e => { if (drag.current) setView({ scale: drag.current.scale, x: drag.current.tx + e.clientX - drag.current.x, y: drag.current.ty + e.clientY - drag.current.y }); }} onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}>
      <div className="fm-canvas" style={{ width: layout.width, height: layout.height, transform: `translate(${camera.x}px,${camera.y}px) scale(${camera.scale})` }}>
        <svg className="fm-links" width={layout.width} height={layout.height} aria-hidden="true">{layout.boxes.map(box => {
          const head = box.machine.id === 'head', center = box.x + 330;
          return <g key={box.machine.id} className={node?.machine.id === box.machine.id ? 'fm-lit' : ''}>
            {!head && <path d={`M${layout.width / 2} ${layout.boxes[0].h + 20} V${box.y - 45} H${center} V${box.y}`} />}
            {(head || !collapsed.has(box.machine.id)) && box.machine.nodes.map((n, i) => { const p = position(i, box.machine.nodes.length, head); return <path key={n.id} className={selected === n.id ? 'fm-lit' : ''} d={i < 3 ? `M${center} ${box.y + (head ? 177 : 0)} V${box.y + p.y - 28} H${box.x + p.x} V${box.y + p.y}` : `M${center} ${box.y + (head ? 185 : 90)} H${box.x + 16} V${box.y + p.y - 28} H${box.x + p.x} V${box.y + p.y}`} />; })}
            {head && <path d={`M${center} ${box.y + 177} V${box.y + box.h}`} />}
          </g>;
        })}</svg>
        {layout.boxes.map(box => <div key={box.machine.id} className={`fm-host fm-${box.machine.kind}`} style={{ left: box.x, top: box.y, width: box.w, height: box.h }}>
          <div className="fm-host-title"><Icon name="nodes" /><div><strong>{box.machine.name}</strong><small>{box.machine.address}</small></div></div><div className="fm-host-tag"><span>{box.machine.kind === 'head' ? 'CONTROL PLANE' : box.machine.kind.toUpperCase()}</span>{box.machine.id !== 'head' && <button aria-label={`${collapsed.has(box.machine.id) ? 'Expand' : 'Collapse'} ${box.machine.name}`} aria-expanded={!collapsed.has(box.machine.id)} onClick={() => toggle(box.machine)}>{collapsed.has(box.machine.id) ? '+' : '−'}</button>}</div>
          {box.machine.id === 'head' && <button className={`fm-node fm-head-node ${selected === 'head' ? 'selected' : ''}`} style={{ left: 235, top: 74 }} aria-label="hearth head" aria-pressed={selected === 'head'} onClick={() => setSelected('head')}><span className="fm-glyph"><Icon name="hearth" /></span><strong>hearth head</strong><small>Routing · identity · scheduling</small></button>}
          {(box.machine.id === 'head' || !collapsed.has(box.machine.id)) && box.machine.nodes.map((n, i) => { const p = position(i, box.machine.nodes.length, box.machine.id === 'head'); return <button className={`fm-node ${selected === n.id ? 'selected' : ''}`} key={n.id} style={{ left: p.x - 95, top: p.y }} aria-pressed={selected === n.id} aria-label={`${n.name}${n.model ? ' · ' + n.model : ''}`} onClick={() => setSelected(n.id)}><span className="fm-glyph"><Icon name={n.icon} /><i className={`fm-dot fm-state-${error ? 'unknown' : n.residency}`} /></span><strong>{n.name}</strong><small style={{ visibility: showModels || !n.model ? 'visible' : 'hidden' }}>{n.model || n.capability}</small><span className="fm-node-state">{error ? 'Observation stale' : labels[n.residency]}{!n.verified ? ' · unverified' : ''}</span></button>; })}
          <div className="fm-host-footer">{box.machine.pools.length ? box.machine.pools.map(pool => <span key={pool.id}>{pool.name} · {pool.policy === 'shared' ? 'shared GPU · ' : ''}{error ? 'state stale' : pool.state} · {pool.queued} queued</span>) : <span>{box.machine.id === 'head' ? 'Built-in capabilities' : 'No capability bindings'}</span>}</div>
        </div>)}
      </div>
    </div><div className="fm-controls"><button aria-label="Zoom out" onClick={() => zoom(1 / 1.2)}>−</button><span>{Math.round(camera.scale * 100)}%</span><button aria-label="Zoom in" onClick={() => zoom(1.2)}>+</button><button onClick={() => setView(null)}>Fit map</button></div></div>
      <aside className="fm-inspector" aria-label="Selected node details"><p className="eyebrow">INSPECTOR</p><Icon name={node?.icon || unassigned?.icon || 'hearth'} /><h2>{node?.name || unassigned?.name || 'hearth head'}</h2><p className="fm-code">{node?.capability || unassigned?.id || data.machines[0]?.address}</p>
        {node ? <><p className="fm-observation">{error ? 'Stale observation' : labels[node.residency]}</p><dl><dt>Machine / address</dt><dd>{node.machine.name} · {node.machine.address}</dd>{node.model && <><dt>Model target</dt><dd>{node.model}</dd><dt>Endpoint</dt><dd>{node.endpoint}</dd><dt>Resource pool</dt><dd>{node.pool}</dd><dt>Saved qualification</dt><dd>{node.verified ? 'Verified for this capability' : 'Needs verification'} · priority {node.priority}</dd><dt>Last verification</dt><dd>{date(node.verified_at)}</dd></>}<dt>Residency observed</dt><dd>{node.residency === 'builtin' ? 'Provided by the head' : date(node.observed_at)}</dd></dl><p className="small-copy">{node.residency === 'on_demand' ? 'The shared queue prepares this backend when its job is selected.' : node.residency === 'unknown' ? 'This provider does not expose confirmed residency, or its read-only inventory could not be reached. Saved verification is separate.' : node.residency === 'builtin' ? 'Private notes and chat history in the head database.' : 'Residency is an observation, not a capacity reservation or a new verification test.'}</p></> : unassigned ? <p className="small-copy">No dedicated binding. {unassigned.id.startsWith('audio.') ? 'Connect a compatible audio provider in Providers.' : 'Automatic text routing falls back to Conversation; explicit specialist selection requires an assignment.'}</p> : <><p className="fm-observation">Connected to control plane</p><p className="small-copy">Capabilities are separate nodes even when they share a model. Each dotted boundary groups endpoints by their saved host address.</p><p className="small-copy">Managed services use fresh worker heartbeats. LM Studio uses read-only loaded-instance inventory, cached up to 15 seconds. Other providers show residency as unknown.</p><p className="small-copy">Address aliases may create separate host groups. Resource pools represent shared capacity, not physical identity.</p></>}
      </aside></div>}
    {showUnassigned && data && <div className="fm-unassigned"><p className="small-copy">Capabilities without a dedicated binding</p>{data.unassigned.map(n => <button className="quiet-button" key={n.id} onClick={() => setSelected(n.id)}>{n.name}</button>)}{!!data.unbound_targets.length && <><p className="small-copy">Connected targets without capability bindings</p>{data.unbound_targets.map(t => <p key={t.target_id} className="small-copy">{t.provider} · {t.model} · {t.machine} · {labels[t.residency]}</p>)}</>}</div>}
    <div className="fm-legend"><span>● Loaded / service ready</span><span>◌ On demand</span><span>□ Dotted boundary: endpoint host</span><span>{error ? 'Updates unavailable' : data ? `Updated ${date(data.observed_at)} · refreshes every 10 seconds` : 'Waiting for snapshot'}</span></div>
  </section>;
}
