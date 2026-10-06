import { expect, test } from '@playwright/test'
import { account } from './helpers'

test('桌面端侧边栏可以收起和展开，并记住上次选择', async ({ page }) => {
  await account(page)
  await page.goto('/')
  const sidebar = page.locator('#main-sidebar')
  const workspaceX = async () => (await page.locator('.workspace').boundingBox())!.x
  await expect(sidebar).toBeInViewport()
  await expect(page.getByRole('button', { name: '收起侧边栏' })).toBeVisible()
  expect(await workspaceX()).toBeGreaterThan(150)

  await page.getByRole('button', { name: '收起侧边栏' }).click()
  await expect(sidebar).not.toBeInViewport()
  await expect(page.getByRole('button', { name: '展开侧边栏' })).toBeVisible()
  await expect.poll(workspaceX).toBe(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true)
  await page.screenshot({ path: test.info().outputPath('sidebar-collapsed.png'), animations: 'disabled' })

  await page.reload()
  await expect(sidebar).not.toBeInViewport()
  await page.getByRole('button', { name: '展开侧边栏' }).click()
  await expect(sidebar).toBeInViewport()
  await page.reload()
  await expect(sidebar).toBeInViewport()

  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByRole('button', { name: '收起侧边栏' })).not.toBeVisible()
  await page.getByRole('button', { name: '展开导航' }).click()
  await expect(sidebar).toBeInViewport()
})
