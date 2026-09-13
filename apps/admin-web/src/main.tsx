import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { EntryShell } from '@hearth/ui';
import '@hearth/ui/theme.css';

createRoot(document.getElementById('root')!).render(<StrictMode><EntryShell audience='admin' /></StrictMode>);
