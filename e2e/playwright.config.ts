import { defineConfig } from '@playwright/test'
import fs from 'fs'
import path from 'path'

const dbPath = path.resolve(__dirname, 'test.db')
const backendDir = path.resolve(__dirname, '..', 'backend')

// Use venv uvicorn if available (local dev), otherwise bare uvicorn (CI)
const venvUvicorn = path.resolve(backendDir, '.venv', 'bin', 'uvicorn')
const uvicorn = fs.existsSync(venvUvicorn) ? venvUvicorn : 'uvicorn'

export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  retries: 0,
  workers: 1,  // serial execution — tests share a single DB
  use: {
    baseURL: 'http://localhost:5173',
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
      command: `SECRET_KEY=test-secret ENABLE_LOCAL_BACKEND=true DATABASE_URL=sqlite+aiosqlite:///${dbPath} ${uvicorn} sheeetz.main:app --port 8000`,
      cwd: backendDir,
      port: 8000,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: 'npx vite --port 5173',
      cwd: path.resolve(__dirname, '..', 'frontend'),
      port: 5173,
      reuseExistingServer: !process.env.CI,
    },
  ],
})
