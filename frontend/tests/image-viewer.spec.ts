import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { account, item, picture } from './helpers'

test.beforeEach(async ({ page }) => {
  await account(page)
  const media = []
  for (const file of [
    { name: '长题图.png', mimeType: 'image/png', buffer: readFileSync(new URL('./fixtures/question-tall.png', import.meta.url)) },
    picture,
  ]) {
    const response = await page.request.post('/api/v1/media', { multipart: { file } })
    expect(response.status()).toBe(201)
    media.push((await response.json()).id)
  }
  const record = await item(page, { title: '需要放大阅读的长题图', question_media: media, answer_media: [media[1]] })
  await page.goto(`/review?item=${record.id}`)
  await expect(page.getByRole('button', { name: '放大图片 1', exact: true })).toBeVisible()
})

test('图片独立放大、拖动、原始大小、适应窗口和切图，关闭后可继续复习', async ({ page, isMobile }) => {
  if (isMobile) await page.setViewportSize({ width: 320, height: 740 })
  await page.getByRole('button', { name: '放大图片 1', exact: true }).click()
  const dialog = page.getByRole('dialog')
  const image = dialog.getByRole('region', { name: '图片查看区域' }).getByRole('img')
  const stage = dialog.getByRole('region', { name: '图片查看区域' })
  const zoomIn = dialog.getByRole('button', { name: '放大图片', exact: true })
  await expect(zoomIn).toBeEnabled()
  const fitted = (await image.boundingBox())!
  const pageWidth = await page.evaluate(() => window.innerWidth)
  await zoomIn.click()
  await expect.poll(async () => (await image.boundingBox())!.width).toBeGreaterThan(fitted.width * 1.2)
  await dialog.getByRole('button', { name: '缩小图片', exact: true }).click()
  await expect.poll(async () => Math.abs((await image.boundingBox())!.width - fitted.width)).toBeLessThan(1)
  await dialog.getByRole('button', { name: '原始大小' }).click()
  await expect(dialog.getByLabel('图片缩放比例')).toHaveText('100%')
  const original = (await image.boundingBox())!
  expect(original.width).toBe(await image.evaluate(img => (img as HTMLImageElement).naturalWidth))
  expect(original.height).toBeGreaterThan((await stage.boundingBox())!.height)

  const bounds = (await stage.boundingBox())!
  const start = { x: bounds.x + bounds.width / 2, y: bounds.y + bounds.height / 2 }
  if (isMobile) {
    const session = await page.context().newCDPSession(page)
    await session.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [start] })
    await session.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: start.x - 70, y: start.y - 80 }] })
    await session.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
    await session.detach()
  } else {
    await page.mouse.move(start.x, start.y)
    await page.mouse.down()
    await page.mouse.move(start.x - 70, start.y - 80, { steps: 5 })
    await page.mouse.up()
  }
  await expect.poll(async () => (await image.boundingBox())!.x).toBeLessThan(original.x - 50)
  await expect.poll(async () => (await image.boundingBox())!.y).toBeLessThan(original.y - 60)
  await page.screenshot({ path: test.info().outputPath('image-viewer-enlarged.png') })
  await dialog.getByRole('button', { name: '适应窗口' }).click()
  await expect.poll(async () => Math.abs((await image.boundingBox())!.width - fitted.width)).toBeLessThan(1)
  expect(await page.evaluate(() => window.innerWidth)).toBe(pageWidth)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true)
  await expect(dialog.getByRole('button', { name: '关闭', exact: true })).toBeInViewport()
  await page.screenshot({ path: test.info().outputPath('image-viewer-fit.png') })

  await zoomIn.click()
  await dialog.getByRole('button', { name: '下一张' }).click()
  await expect(dialog).toHaveAccessibleName('图片 2 / 2')
  await expect(image).toHaveAttribute('alt', picture.name)
  await expect(zoomIn).toBeEnabled()
  await expect(dialog.getByRole('button', { name: '下一张' })).toBeDisabled()
  const second = (await image.boundingBox())!
  expect(second.width).toBeLessThanOrEqual(bounds.width + 1)
  expect(second.height).toBeLessThanOrEqual(bounds.height + 1)
  await dialog.getByRole('button', { name: '上一张' }).click()
  await expect.poll(async () => Math.abs((await image.boundingBox())!.width - fitted.width)).toBeLessThan(1)
  if (isMobile) await dialog.getByRole('button', { name: '关闭', exact: true }).click()
  else await page.keyboard.press('Escape')
  await expect(dialog).not.toBeVisible()
  await page.getByRole('button', { name: /查看答案/ }).click()
  await page.locator('.revealed-answer').getByRole('button', { name: '放大图片 1', exact: true }).click()
  await expect(dialog).toHaveAccessibleName('图片 1 / 1')
  await expect(dialog.getByRole('button', { name: '放大图片', exact: true })).toBeEnabled()
  await dialog.getByRole('button', { name: '关闭', exact: true }).click()
  await expect(page.getByRole('button', { name: /良好/ })).toBeVisible()
})

test('Ctrl 加滚轮从题图打开查看器并只缩放图片，普通滚轮和键盘也可操作', async ({ page, isMobile }) => {
  test.skip(isMobile, 'Ctrl+滚轮为桌面交互，手机使用缩放按钮和触摸拖动')
  const thumbnail = page.getByRole('button', { name: '放大图片 1', exact: true })
  await thumbnail.hover()
  const browserSize = await page.evaluate(() => ({ width: innerWidth, ratio: devicePixelRatio }))
  await page.evaluate(() => window.addEventListener('wheel', event => {
    document.documentElement.dataset.wheelPrevented = String(event.defaultPrevented)
  }))
  await page.keyboard.down('Control')
  await page.mouse.wheel(0, -120)
  await page.keyboard.up('Control')
  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible()
  await expect(page.locator('html')).toHaveAttribute('data-wheel-prevented', 'true')
  const image = dialog.getByRole('region', { name: '图片查看区域' }).getByRole('img')
  await expect(dialog.getByRole('button', { name: '放大图片', exact: true })).toBeEnabled()
  const stage = dialog.getByRole('region', { name: '图片查看区域' })
  await expect.poll(async () => (await image.boundingBox())!.height).toBeGreaterThan((await stage.boundingBox())!.height * 1.2)
  const before = (await image.boundingBox())!
  await stage.hover()
  await page.keyboard.down('Control')
  await page.mouse.wheel(0, -120)
  await page.keyboard.up('Control')
  await expect.poll(async () => (await image.boundingBox())!.width).toBeGreaterThan(before.width * 1.2)
  await expect(page.locator('html')).toHaveAttribute('data-wheel-prevented', 'true')
  expect(await page.evaluate(() => ({ width: innerWidth, ratio: devicePixelRatio }))).toEqual(browserSize)
  const enlarged = (await image.boundingBox())!.width
  await page.mouse.wheel(0, 120)
  await expect.poll(async () => (await image.boundingBox())!.width).toBeLessThan(enlarged * .9)
  await stage.focus()
  await page.keyboard.press('1')
  await expect(dialog.getByLabel('图片缩放比例')).toHaveText('100%')
  await page.keyboard.press('+')
  await expect(dialog.getByLabel('图片缩放比例')).toHaveText('125%')
  await page.keyboard.press('0')
  expect((await image.boundingBox())!.height).toBeLessThanOrEqual((await stage.boundingBox())!.height + 1)
  // Review shortcuts must remain inactive while inspecting a question image.
  await page.keyboard.press('Space')
  await expect(page.locator('.revealed-answer')).not.toBeVisible()
})
