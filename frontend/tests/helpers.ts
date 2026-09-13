import { expect, type Page } from '@playwright/test'
import { randomUUID } from 'node:crypto'
import { readFileSync } from 'node:fs'

export const password = 'shiyi-browser-test-2026'
export const picture = {
  name: '题目截图.png',
  mimeType: 'image/png',
  buffer: readFileSync(new URL('./fixtures/question.png', import.meta.url)),
}

export async function account(page: Page) {
  const username = 'e2e-' + randomUUID().slice(0, 12)
  const result = await page.request.post('/api/v1/auth/register', { data: { username, password, display_name: '测试同学' } })
  expect(result.status()).toBe(201)
  return result.json()
}

export async function item(page: Page, fields: Record<string, unknown> = {}) {
  const result = await page.request.post('/api/v1/items', { data: {
    title: 'Cache 组数与地址划分', subject: '408', question: '已知 Cache 容量、块大小和路数，如何计算组数？',
    answer: '组数 = 容量 /（块大小 × 路数）。先统一容量单位。', ...fields,
  } })
  expect(result.status()).toBe(201)
  return result.json()
}

export async function openEditor(page: Page, mistake = false) {
  await page.goto(mistake ? '/mistakes' : '/library')
  await page.getByRole('button', { name: mistake ? '收录错题' : '记录新知', exact: true }).last().click()
  return page.getByRole('dialog')
}
