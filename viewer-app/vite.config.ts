import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // The repo-root .env is the single source of config for all three
  // subprojects, and README's quick start creates it there.
  envDir: '..',
})
