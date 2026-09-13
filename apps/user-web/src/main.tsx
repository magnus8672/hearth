import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { Application } from '../../../packages/ui/src/application';
import '@hearth/ui/theme.css';

createRoot(document.getElementById('root')!).render(<StrictMode><Application audience='user' /></StrictMode>);
