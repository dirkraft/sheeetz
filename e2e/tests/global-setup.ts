import { test as setup } from '@playwright/test'
import { execSync } from 'child_process'
import fs from 'fs'
import path from 'path'

const BACKEND_DIR = path.resolve(__dirname, '..', '..', 'backend')
const DB_PATH = path.resolve(__dirname, '..', 'test.db')
const FIXTURES_DIR = path.resolve(BACKEND_DIR, 'tests', 'fixtures')
const SEED_SCRIPT = path.resolve(__dirname, '..', 'seed.py')
const AUTH_FILE = path.resolve(__dirname, '..', 'auth.json')
const SECRET_KEY = 'test-secret'

// Use venv python if available (local dev), otherwise system python3 (CI)
const venvPython = path.resolve(BACKEND_DIR, '.venv', 'bin', 'python3')
const python = fs.existsSync(venvPython) ? venvPython : 'python3'

setup('seed database and save auth state', async ({ browser }) => {
  // Remove stale DB
  if (fs.existsSync(DB_PATH)) fs.unlinkSync(DB_PATH)

  // Run seed script to create DB and get auth token
  const out = execSync(
    `${python} ${SEED_SCRIPT} ${DB_PATH} ${FIXTURES_DIR} ${SECRET_KEY}`,
    { encoding: 'utf-8' },
  )
  const seed = JSON.parse(out.trim())

  // Save auth info for test files
  fs.writeFileSync(AUTH_FILE, JSON.stringify(seed))

  // Create a browser context with the session cookie and save storage state
  const context = await browser.newContext()
  await context.addCookies([
    {
      name: 'session_token',
      value: seed.token,
      domain: 'localhost',
      path: '/',
    },
  ])
  await context.storageState({ path: path.resolve(__dirname, '..', 'storage-state.json') })
  await context.close()
})
