import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Relative base so the build works from GitHub Pages or a Capacitor webview.
export default defineConfig({
  base: './',
  plugins: [react()],
});
