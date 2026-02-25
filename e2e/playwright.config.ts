import { defineConfig } from '@playwright/test'
import fs from 'fs'
import path from 'path'

const dbPath = path.resolve(__dirname, 'test.db')
const backendDir = path.resolve(__dirname, '..', 'backend')
const frontendDir = path.resolve(__dirname, '..', 'frontend')

// Use venv uvicorn if available (local dev), otherwise bare uvicorn (CI)
const venvUvicorn = path.resolve(backendDir, '.venv', 'bin', 'uvicorn')
const uvicorn = fs.existsSync(venvUvicorn) ? venvUvicorn : 'uvicorn'

// Use separate ports so e2e tests don't conflict with running dev servers
const backendPort = 8001
const frontendPort = 5174

export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  retries: 0,
  workers: 1,  // serial execution — tests share a single DB
  use: {
    baseURL: `http://localhost:${frontendPort}`,
    headless: true,
  },
  projects: [
    { name: 'setup', testMatch: 'global-setup.ts' },
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
      dependencies: ['setup'],
    },
  ],
  webServer: [
    {
      command: `SECRET_KEY=test-secret ENABLE_LOCAL_BACKEND=true DATABASE_URL=sqlite+aiosqlite:///${dbPath} ${uvicorn} sheeetz.main:app --port ${backendPort}`,
      cwd: backendDir,
      port: backendPort,
      reuseExistingServer: false,
    },
    {
      command: `npx vite --port ${frontendPort}`,
      cwd: frontendDir,
      port: frontendPort,
      env: { VITE_API_TARGET: `http://localhost:${backendPort}` },
      reuseExistingServer: false,
    },
  ],
})
