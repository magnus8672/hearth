import { useEffect, useState } from 'react';
import { api, mutation, type Identity } from './api';
import { Status } from './index';

type Account = { id: string; display_name: string; state: string; roles: string[]; permissions: string[]; revision: number };
type Catalog = { items: Account[]; capabilities: { permission: string; name: string }[] };
const features = [['conversation.own', 'Private chat and side notes'], ['channel.use', 'Shared channels'], ['draft.use', 'Private drafts'], ['tool.use', 'Shared tools'], ['api_key.own', 'Client API keys']];

export function Accounts({ identity }: { identity: Identity }) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [selected, setSelected] = useState<Account | null>(null);
  const [state, setState] = useState('active');
  const [role, setRole] = useState('Member');
  const [permissions, setPermissions] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const canManage = identity.permissions.includes('role.grant');
  async function refresh() { setCatalog(await api<Catalog>('/api/v1/accounts')); }
  useEffect(() => { if (canManage) void refresh().catch(reason => setError(reason.message)); }, [canManage]);
  if (!canManage) return <section className="panel"><h2>Account management</h2><p>An Owner or farm administrator can approve accounts and grant capabilities.</p></section>;
  function edit(account: Account) { setSelected(account); setState(account.state === 'pending' ? 'active' : account.state); setRole(account.roles[0] || 'Member'); setPermissions(account.permissions); setError(''); setNotice(''); }
  function toggle(permission: string, checked: boolean) { setPermissions(previous => checked ? [...new Set([...previous, permission])] : previous.filter(item => item !== permission)); }
  async function save() {
    if (!selected || busy) return;
    setBusy(true); setError(''); setNotice('');
    try {
      await api(`/api/v1/accounts/${selected.id}/access`, mutation(identity, { revision: selected.revision, state, role, permissions }, 'PUT'));
      await refresh(); setSelected(null); setNotice('Access saved. The person can choose Check access or sign in again. Previous sessions and client keys are no longer authorized.');
    } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); }
  }
  return <><div className="info-banner"><p>New accounts wait for approval. Grant only the capabilities each person needs. Administration never grants access to someone else’s private conversations or files.</p></div>
    {error && <p className="error-notice" role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    <div className="image-layout accounts-layout"><section className="panel"><div className="section-heading"><h2>Farm accounts</h2><button className="quiet-button" disabled={busy} onClick={() => { setSelected(null); void refresh().catch(reason => setError(reason.message)); }}>Refresh accounts</button></div>
      {catalog?.items.map(account => <div className="person-row" key={account.id}><div><strong>{account.display_name}</strong><span>{account.roles.join(' · ') || 'No access granted'}</span><Status state={account.state === 'active' ? 'ready' : 'offline'}>{account.state === 'pending' ? 'Awaiting approval' : account.state}</Status></div>
        {account.id === identity.id || account.roles.includes('Owner') ? <span className="small-copy">{account.id === identity.id ? 'Your account' : 'Owner · protected'}</span> : <button className="quiet-button" disabled={busy} onClick={() => edit(account)}>{account.state === 'pending' ? 'Review access' : 'Edit access'}</button>}</div>)}
    </section><section className="panel account-editor">{selected ? <form onSubmit={event => { event.preventDefault(); void save(); }}><h2>Access for {selected.display_name}</h2>
      <label>Account status<select value={state} onChange={event => setState(event.target.value)} disabled={busy}><option value="active">Enabled</option><option value="pending">Awaiting approval · workspace only</option><option value="suspended">Suspended · cannot sign in</option></select></label>
      <label>Farm role<select value={role} onChange={event => setRole(event.target.value)} disabled={busy || state === 'pending'}><option value="Member">Member · selected access below</option><option value="FarmAdmin">Farm administrator · all capabilities and user management</option><option value="Operator">Operator · machine operations</option><option value="Auditor">Auditor · farm inspection</option></select></label>
      {role === 'FarmAdmin' && state !== 'pending' ? <p>Farm administrators can configure providers, use all capabilities, approve other users and promote them to administrator. Owner recovery and package approval remain reserved for the Owner.</p> : <fieldset disabled={busy || state === 'pending'}><legend>Workspace permissions</legend>
        <div className="target-actions"><button type="button" className="quiet-button" onClick={() => setPermissions(['conversation.own', 'capability.chat.general'])}>Chat only</button><button type="button" className="quiet-button" onClick={() => setPermissions([...features.map(([key]) => key), ...(catalog?.capabilities.map(item => item.permission) || [])])}>All workspace capabilities</button><button type="button" className="quiet-button" onClick={() => setPermissions([])}>Clear grants</button></div>
        {features.map(([permission, name]) => <label className="check-label" key={permission}><input type="checkbox" checked={permissions.includes(permission)} onChange={event => toggle(permission, event.target.checked)} />{name}</label>)}
        <h3>Capabilities</h3><p className="small-copy">Grant Private chat to use text specialists in the browser. Image and 3D generation can be granted independently. Automatic routing also respects this list.</p>
        {catalog?.capabilities.map(item => <label className="check-label" key={item.permission}><input type="checkbox" checked={permissions.includes(item.permission)} onChange={event => toggle(item.permission, event.target.checked)} />{item.name}</label>)}
      </fieldset>}
      <p className="small-copy">Saving ends this account’s existing sessions, client keys and current work. Saved content is preserved. The next sign-in uses these grants.</p><button className="primary-button" disabled={busy}>{busy ? 'Saving…' : selected.state === 'pending' && state === 'active' ? 'Enable account' : 'Save access'}</button>
    </form> : <><h2>Make room for someone.</h2><p>Select an account to approve it, adjust its capabilities or suspend access.</p><p>Invite people to <a href={identity.user_origin.replace('https:', 'http:')}>the welcome and certificate page</a>. They set up their password and authenticator before appearing here.</p></>}</section></div></>;
}
