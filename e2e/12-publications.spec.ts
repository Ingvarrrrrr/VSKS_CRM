import { test, expect } from '@playwright/test'
import { login } from './helpers'

const BASE_URL = process.env.BASE_URL || 'http://localhost'

test.describe('Publications & Email', () => {
  let purchaseId: number
  let token: string

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage()
    await login(page)
    token = await page.evaluate(() => localStorage.getItem('auth_token') || '')

    // Получить первую закупку для тестов (trailing slash чтобы избежать 307 редиректа)
    const resp = await page.request.get(`${BASE_URL}/api/purchases/?limit=5`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(resp.ok(), `GET /api/purchases/ should return 200, got ${resp.status()}`).toBeTruthy()
    const purchases = await resp.json()
    expect(purchases.length).toBeGreaterThan(0)
    purchaseId = purchases[0].id
    await page.close()
  })

  test('Фабрикант test mode: mock callback → status=published, chip виден в UI', async ({ page, request }) => {
    await login(page)
    const tok = await page.evaluate(() => localStorage.getItem('auth_token') || '')

    // 1. Создать публикацию на Фабрикант (или получить существующую при 409)
    const pubResp = await request.post(`${BASE_URL}/api/publications/purchases/${purchaseId}`, {
      data: { platform: 'fabrikant' },
      headers: { Authorization: `Bearer ${tok}` },
    })
    // 200 = создана; 409 = уже есть активная — найдём её
    expect([200, 409], `Expected 200 or 409, got ${pubResp.status()}`).toContain(pubResp.status())

    let pub: { id: number; status: string; external_id?: string }
    if (pubResp.status() === 409) {
      // Получаем существующую публикацию для этой закупки на fabrikant
      const listResp = await request.get(`${BASE_URL}/api/publications/purchases/${purchaseId}`, {
        headers: { Authorization: `Bearer ${tok}` },
      })
      expect(listResp.ok()).toBeTruthy()
      const pubs = await listResp.json()
      const existing = pubs.find((p: any) => p.platform === 'fabrikant')
      expect(existing, 'Должна быть существующая публикация на fabrikant').toBeTruthy()
      pub = existing
    } else {
      pub = await pubResp.json()
    }
    expect(pub.id, 'publication должна иметь id').toBeTruthy()

    // 2. Mock n8n callback — симулируем ответ от Фабрикант (test mode success)
    const callbackResp = await request.patch(`${BASE_URL}/api/publications/${pub.id}/status`, {
      data: {
        status: 'published',
        external_id: 'TEST-FAB-' + Date.now(),
        external_url: 'https://fabrikant.ru/test-lot',
      },
      headers: { Authorization: `Bearer ${tok}` },
    })
    expect(callbackResp.status(), 'PATCH callback should return 200').toBe(200)
    const updated = await callbackResp.json()
    expect(updated.status).toBe('published')
    expect(updated.external_id).toMatch(/TEST-FAB-/)

    // 3. Проверить в UI что chip "Опубликовано" виден
    await page.goto(`/orders/${purchaseId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1500)

    // Ищем chip или текст "Опубликовано" в секции публикаций
    const publishedEl = page.locator('.v-chip').filter({ hasText: /Опубликовано/i }).first()
    await expect(publishedEl, 'chip "Опубликовано" должен быть виден').toBeVisible({ timeout: 8000 })
  })

  test('Росэлторг — нет токена: error_text виден в таблице публикаций', async ({ page, request }) => {
    await login(page)
    const tok = await page.evaluate(() => localStorage.getItem('auth_token') || '')

    // 1. Создать публикацию на Росэлторг с procedure_type (или получить существующую при 409)
    const pubResp = await request.post(`${BASE_URL}/api/publications/purchases/${purchaseId}`, {
      data: { platform: 'roseltorg_rb', procedure_type: 'request_quotations' },
      headers: { Authorization: `Bearer ${tok}` },
    })
    expect([200, 409], `Expected 200 or 409, got ${pubResp.status()}`).toContain(pubResp.status())

    let pub: { id: number; status: string }
    if (pubResp.status() === 409) {
      const listResp = await request.get(`${BASE_URL}/api/publications/purchases/${purchaseId}`, {
        headers: { Authorization: `Bearer ${tok}` },
      })
      expect(listResp.ok()).toBeTruthy()
      const pubs = await listResp.json()
      const existing = pubs.find((p: any) => p.platform === 'roseltorg_rb')
      expect(existing, 'Должна быть существующая публикация на roseltorg_rb').toBeTruthy()
      pub = existing
    } else {
      pub = await pubResp.json()
    }

    // 2. Mock n8n callback — симулируем error (нет токена)
    const errorText = 'Требуется Bearer Token Росэлторг — настройте в параметрах n8n (переменная ROSELTORG_TOKEN)'
    const callbackResp = await request.patch(`${BASE_URL}/api/publications/${pub.id}/status`, {
      data: { status: 'error', error_text: errorText },
      headers: { Authorization: `Bearer ${tok}` },
    })
    expect(callbackResp.status(), 'PATCH error callback should return 200').toBe(200)
    const updated = await callbackResp.json()
    expect(updated.status).toBe('error')
    expect(updated.error_text).toContain('Требуется Bearer Token')

    // 3. Проверить в UI что error_text виден на странице закупки
    await page.goto(`/orders/${purchaseId}/edit`)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1500)

    // Error text должен быть виден где-то на странице (в таблице публикаций)
    const errorEl = page.locator('text=Требуется Bearer Token').first()
    await expect(errorEl, 'error_text "Требуется Bearer Token" должен быть виден в UI').toBeVisible({ timeout: 8000 })
  })

  test('Росэлторг API принимает procedure_type без ошибки валидации', async ({ request, page }) => {
    await login(page)
    const tok = await page.evaluate(() => localStorage.getItem('auth_token') || '')

    // POST с procedure_type не должен возвращать 422
    const resp = await request.post(`${BASE_URL}/api/publications/purchases/${purchaseId}`, {
      data: { platform: 'roseltorg_rb', procedure_type: 'auction' },
      headers: { Authorization: `Bearer ${tok}` },
    })
    // 200 = ok; 409 = уже опубликовано (тоже приемлемо в контексте теста)
    expect([200, 409], `Expected 200 or 409, got ${resp.status()}`).toContain(resp.status())
  })

  test('SMTP test endpoint отвечает без 500 ошибки', async ({ request, page }) => {
    await login(page)
    const tok = await page.evaluate(() => localStorage.getItem('auth_token') || '')

    // POST /api/settings/smtp/test
    // На сервере с настроенным SMTP → 200
    // На локальной машине без SMTP → 400 с понятным сообщением
    // В любом случае НЕ 500
    const resp = await request.post(
      `${BASE_URL}/api/settings/smtp/test?to_email=zakupki@vsks.ru`,
      { headers: { Authorization: `Bearer ${tok}` } }
    )
    expect(resp.status(), 'SMTP test endpoint должен вернуть 200 или 400, не 500').not.toBe(500)

    // Если 400 — проверить что в теле есть понятное сообщение (не пустое)
    if (resp.status() === 400) {
      const body = await resp.json()
      expect(body.detail || body.message || body.error, 'Сообщение об ошибке SMTP должно быть непустым').toBeTruthy()
    }
  })
})
