import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({ plugins: [react()], server: { proxy: { '/health': { target: process.env.HEARTH_DEV_API || 'http://127.0.0.1:18080' } } } });
