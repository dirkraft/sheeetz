import { test as base } from '@playwright/test'
import path from 'path'

export const test = base.extend({
  storageState: path.resolve(__dirname, '..', 'storage-state.json'),
})

export { expect } from '@playwright/test'
