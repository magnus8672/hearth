// Local fixture defaults; remote runs supply their deployment origins privately.
const workspace = process.env.HEARTH_BROWSER_ORIGIN || 'http://127.0.0.1:5174';
function related(port: string, protocol?: string) {
  const url = new URL(workspace);
  if (protocol) url.protocol = protocol;
  url.port = port;
  return url.origin;
}
export const browserOrigins = {
  workspace,
  admin: process.env.HEARTH_ADMIN_BROWSER_ORIGIN || (process.env.HEARTH_BROWSER_ORIGIN ? related('8443') : 'http://127.0.0.1:5173'),
  identity: process.env.HEARTH_IDENTITY_BROWSER_ORIGIN || related('8445'),
  welcome: process.env.HEARTH_WELCOME_BROWSER_ORIGIN || related('', 'http:'),
};
