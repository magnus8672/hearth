import { useEffect, useState, type ReactNode } from 'react';
import lightLockup from '../../../brand/logos/hearth-lockup-light.svg';
import darkLockup from '../../../brand/logos/hearth-lockup-dark.svg';
import iconSprite from '../../../brand/icons/hearth-icons.svg';

export type Theme = 'system' | 'light' | 'dark';

export function Icon({ name, className = '' }: { name: string; className?: string }) {
  return <svg className={`icon ${className}`} aria-hidden="true" viewBox="0 0 24 24"><use href={`${iconSprite}#hearth-${name}`} /></svg>;
}

export function Brand() {
  return <span className="brand"><img className="brand-light" src={lightLockup} alt="Hearth" /><img className="brand-dark" src={darkLockup} alt="Hearth" /></span>;
}

export function ThemeControl() {
  const [theme, setTheme] = useState<Theme>(() => (document.documentElement.dataset.theme as Theme) || 'system');
  function change(next: Theme) {
    setTheme(next);
    if (next === 'system') delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = next;
    try { localStorage.setItem('hearth.theme', next); } catch { /* The choice still applies in a private window. */ }
  }
  return <label className="theme-control"><Icon name={theme === 'dark' ? 'moon' : 'sun'} /><span className="sr-only">Appearance</span>
    <select aria-label="Appearance" value={theme} onChange={event => change(event.target.value as Theme)}>
      <option value="system">System</option><option value="light">Daylight</option><option value="dark">Firelight</option>
    </select>
  </label>;
}

export function Status({ state, children }: { state: 'ready' | 'warming' | 'offline' | 'unassigned' | 'failed'; children: ReactNode }) {
  return <span className={`status status-${state}`}><Icon name={state} />{children}</span>;
}

type Connection = 'checking' | 'ready' | 'unavailable';

export function useControlConnection() {
  const [state, setState] = useState<Connection>('checking');
  const [generation, setGeneration] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 4500);
    let active = true;
    setState('checking');
    fetch('/health/ready', { signal: controller.signal, cache: 'no-store', credentials: 'omit' })
      .then(async response => {
        if (!response.ok) throw new Error('Control plane unavailable');
        const payload: unknown = await response.json();
        if (typeof payload !== 'object' || payload === null || !('status' in payload) || payload.status !== 'ready') throw new Error('Invalid readiness response');
        if (active) setState('ready');
      })
      .catch(() => { if (active) setState('unavailable'); })
      .finally(() => window.clearTimeout(timeout));
    return () => { active = false; controller.abort(); window.clearTimeout(timeout); };
  }, [generation]);
  return { state, retry: () => setGeneration(value => value + 1) };
}
