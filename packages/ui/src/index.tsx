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

export function EntryShell({ audience }: { audience: 'admin' | 'user' }) {
  const { state, retry } = useControlConnection();
  const admin = audience === 'admin';
  return <div className="entry-shell">
    <a className="skip-link" href="#main">Skip to content</a>
    <header className="app-header"><a className="home-link" href="/" aria-label="Hearth home"><Brand /></a>
      <span className="app-kind">{admin ? 'Administration' : 'Your workspace'}</span><ThemeControl />
    </header>
    <main id="main" className="entry-main">
      <div className="welcome-copy">
        <p className="eyebrow"><Icon name="hearth" /> AGENTIC CLOUD AT HOME</p>
        <h1>{admin ? <>Make yourself<br />at home.</> : <>A place for<br />your ideas.</>}</h1>
        <p className="lead">{admin ? 'Bring your machines together. Keep your intelligence close.' : 'Think, write, and make with an assistant that belongs at home.'}</p>
        <div className="principles">
          <div><Icon name="lock" /><span>Private by default</span></div>
          <div><Icon name="nodes" /><span>Your machines, working together</span></div>
          <div><Icon name="settings" /><span>You stay in control</span></div>
        </div>
      </div>
      <section className="entry-card" aria-labelledby="entry-title">
        <div className="card-mark"><Icon name={admin ? 'hearth' : 'chat'} /></div>
        <p className="eyebrow">{admin ? 'YOUR HEARTH' : 'WELCOME HOME'}</p>
        <h2 id="entry-title">{admin ? 'A strong foundation.' : 'Room to begin.'}</h2>
        <p>{admin ? 'This Hearth is being built. The control plane and shared contracts come first, followed by secure account setup.' : 'Your private workspace will be available once account setup is connected.'}</p>
        <div className="connection-panel" aria-live="polite" aria-atomic="true">
          <div className="connection-label">Control plane</div>
          <Status state={state === 'ready' ? 'ready' : state === 'checking' ? 'warming' : 'offline'}>
            {state === 'ready' ? 'Database connected' : state === 'checking' ? 'Checking connection' : 'Connection unavailable'}
          </Status>
          <p>{state === 'ready' ? 'The API can reach its database. Account and provider readiness are checked separately.' : state === 'checking' ? 'Checking the API and its database connection.' : 'The control service is not reachable. Start or recover the development appliance, then check again.'}</p>
        </div>
        <button className="primary-button" type="button" disabled={state === 'checking'} onClick={retry}><Icon name="activity" />{state === 'checking' ? 'Checking…' : 'Check connection'}</button>
        <div className="sign-in-pending"><Icon name="lock" /><span>Sign-in is not available in this foundation build.</span></div>
      </section>
      <section className="capability-intro" aria-label="The Hearth product">
        <div><Icon name={admin ? 'node' : 'writing'} /><h3>{admin ? 'One home for your machines' : 'From a thought to a first draft'}</h3><p>{admin ? 'Manage capabilities from one place as your farm grows.' : 'Keep conversations and project context in your own workspace.'}</p></div>
        <div><Icon name={admin ? 'security' : 'knowledge'} /><h3>{admin ? 'A deliberate first step' : 'Knowledge that stays close'}</h3><p>{admin ? 'Owner setup and secure enrollment will establish who and what belongs here.' : 'Bring approved knowledge into your work, with its sources attached.'}</p></div>
        <div><Icon name={admin ? 'cloud' : 'cube'} /><h3>{admin ? 'Local first. Your choice.' : 'Make more than words'}</h3><p>{admin ? 'Connect local inference or opt into a cloud provider with explicit budgets.' : 'Build toward images, speech, and 3D alongside everyday conversations.'}</p></div>
      </section>
    </main>
    <footer className="app-footer"><span>Hearth <span className="footer-dot">·</span> Agentic Cloud at Home</span><span>Foundation build <span className="footer-dot">·</span> 0.1.0</span></footer>
  </div>;
}
