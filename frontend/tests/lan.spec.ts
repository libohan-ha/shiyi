import { expect, test } from '@playwright/test'
import { randomUUID } from 'node:crypto'
import { openEditor, password, picture } from './helpers'

test('HTTP 局域网手机访问可以登录、上传图片、评分和撤销', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/login')
  expect(await page.evaluate(() => window.isSecureContext)).toBe(false)
  expect(await page.evaluate(() => typeof crypto.randomUUID)).toBe('undefined')
  await expect(page.getByLabel('用户名')).toBeVisible()
  if (await page.getByRole('button', { name: '创建一个独立的学习账号' }).isVisible()) {
    await page.getByRole('button', { name: '创建一个独立的学习账号' }).click()
  }
  await page.getByLabel('怎么称呼你').fill('局域网同学')
  await page.getByLabel('用户名').fill('lan-' + randomUUID().slice(0, 8))
  await page.locator('input[autocomplete="new-password"]').fill(password)
  await page.getByRole('button', { name: '开始我的积累' }).click()
  await expect(page.getByRole('heading', { name: /局域网同学/ })).toBeVisible()

  const editor = await openEditor(page, true)
  await editor.getByLabel('标题').fill('局域网图片错题')
  await editor.getByLabel('问题 / 题干附件', { exact: true }).setInputFiles(picture)
  await expect(editor.getByAltText('问题 / 题干图片 1')).toBeVisible()
  await editor.getByLabel('答案 / 解析', { exact: true }).fill('在纸上独立解题后，对照这里的参考答案。')
  await editor.getByRole('button', { name: '收进知识库' }).click()
  await expect(editor).not.toBeVisible()
  await page.getByRole('link').filter({ hasText: '局域网图片错题' }).click()
  const id = page.url().split('/').at(-1)!
  await page.getByRole('link', { name: '复习这条知识' }).click()
  await page.getByRole('button', { name: /查看答案/ }).click()
  await page.getByRole('button', { name: /良好/ }).click()
  await expect(page.getByText('今天的努力，已悄悄生根。')).toBeVisible()
  await page.getByRole('button', { name: '撤销上次评分' }).click()
  await expect(page.getByRole('heading', { name: '局域网图片错题' })).toBeVisible()
  await page.getByRole('button', { name: /查看答案/ }).click()
  await page.getByRole('button', { name: /轻松/ }).click()
  await expect(page.getByText('今天的努力，已悄悄生根。')).toBeVisible()
  const history = await page.evaluate(async recordId => (await fetch(`/api/v1/items/${recordId}/reviews`)).json(), id)
  expect(history.total).toBe(2)
  expect(history.items.filter((review: { undone: boolean }) => !review.undone)).toHaveLength(1)
  expect(errors).toEqual([])
})
