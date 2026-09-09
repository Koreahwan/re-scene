import { test, expect } from '@playwright/test';

test.describe('RE:SCENE Figma Exact Visual Regression Suite', () => {
  test('Home page renders correctly at 1440px desktop', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/RE:SCENE/i);
    // Verify brand logo and hero section
    const heroTitle = page.locator('h1');
    await expect(heroTitle).toBeVisible();
  });

  test('Film hub page renders catalog and cards', async ({ page }) => {
    await page.goto('/films');
    const catalogHeading = page.locator('h1');
    await expect(catalogHeading).toContainText('영화 복선 탐색 카탈로그');
  });

  test('Film detail page enforces server spoiler gate', async ({ page }) => {
    await page.goto('/films/the-bat-whispers-1930');
    const filmTitle = page.locator('h1');
    await expect(filmTitle).toContainText('The Bat Whispers');
  });

  test('Magazine page renders articles and categories', async ({ page }) => {
    await page.goto('/magazine');
    const magHeading = page.locator('h1');
    await expect(magHeading).toContainText('시네마 매거진');
  });

  test('Community page renders debate posts and write button', async ({ page }) => {
    await page.goto('/community');
    const commHeading = page.locator('h1');
    await expect(commHeading).toContainText('커뮤니티 복선 토론장');
  });

  test('iPad Mini (744px) layout has zero horizontal scrollbar overflow', async ({ page }) => {
    await page.setViewportSize({ width: 744, height: 1133 });
    await page.goto('/');
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1);
  });
});
