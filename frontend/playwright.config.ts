import { defineConfig, devices } from '@playwright/test'
import { existsSync } from 'node:fs'
import path from 'node:path'

const port = Number(process.env.SHIYI_E2E_PORT || 18765)
const localChrome = process.platform === 'win32' && existsSync('C:/Program Files/Google/Chrome/Application/chrome.exe')
const python = path.resolve('../backend/.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    channel: process.env.PLAYWRIGHT_CHANNEL || (localChrome ? 'chrome' : undefined),
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
  },
  projects: [
    { name: 'desktop', testMatch: ['workflows.spec.ts', 'improvements.spec.ts'], use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 1000 } } },
    { name: 'mobile', testMatch: 'mobile.spec.ts', use: { ...devices['Pixel 7'] } },
    { name: 'lan', testMatch: 'lan.spec.ts', use: {
      ...devices['Pixel 7'],
      baseURL: `http://shiyi-lan.test:${port}`,
      launchOptions: { args: ['--host-resolver-rules=MAP shiyi-lan.test 127.0.0.1', '--no-proxy-server'] },
    } },
  ],
  webServer: {
    command: `"${python}" ../scripts/e2e_server.py`,
    url: `http://127.0.0.1:${port}/api/health`,
    timeout: 60_000,
    reuseExistingServer: false,
    env: { SHIYI_E2E_PORT: String(port) },
  },
})
