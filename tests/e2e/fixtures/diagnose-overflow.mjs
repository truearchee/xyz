#!/usr/bin/env node
// One-off diagnostic: at 375px, list elements wider than the viewport that are NOT contained by any
// clipping (overflow auto/scroll/hidden, clientWidth<=vw) ancestor — i.e. the TRUE page-wideners.
import { chromium } from '@playwright/test';

const BASE = process.env.E2E_BASE_URL ?? 'http://localhost:3000';
const PASSWORD = process.env.E2E_TEST_PASSWORD ?? 'LocalE2EPassword123!';
const TARGETS = [
  { email: 'admin_e2e@example.test', home: '/admin', route: '/admin' },
  {
    email: 'lecturer_e2e@example.test',
    home: '/lecturer',
    route: '/lecturer/modules/20000000-0000-4000-8000-000000000001',
  },
];

async function signIn(page, email, home) {
  await page.goto(`${BASE}/login`);
  await page.waitForFunction(() => typeof window.__xyzE2E !== 'undefined');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.waitForURL(new RegExp(`${home}$`), { timeout: 45000 });
}

const browser = await chromium.launch();
for (const t of TARGETS) {
  const ctx = await browser.newContext({ viewport: { width: 375, height: 812 } });
  const page = await ctx.newPage();
  await signIn(page, t.email, t.home);
  await page.goto(`${BASE}${t.route}`);
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.waitForTimeout(500);
  const res = await page.evaluate(() => {
    const vw = window.innerWidth;
    function containedByClip(el) {
      let p = el.parentElement;
      while (p) {
        const ox = getComputedStyle(p).overflowX;
        if ((ox === 'auto' || ox === 'scroll' || ox === 'hidden') && p.clientWidth <= vw + 1) return true;
        p = p.parentElement;
      }
      return false;
    }
    const out = [];
    for (const el of Array.from(document.querySelectorAll('*'))) {
      if (el.offsetWidth > vw + 1 && getComputedStyle(el).overflowX === 'visible' && !containedByClip(el)) {
        // only the deepest such elements are interesting (a widener whose children are all narrower OR also listed)
        out.push({
          tag: el.tagName.toLowerCase(),
          off: el.offsetWidth,
          testid: el.getAttribute('data-testid') || '',
          type: el.getAttribute('type') || '',
          cls: (el.getAttribute('class') || '').slice(0, 60),
          kids: el.children.length,
        });
      }
    }
    return { vw, docSW: document.documentElement.scrollWidth, out };
  });
  console.log(`\n===== ${t.route} vw=${res.vw} docScrollWidth=${res.docSW} — TRUE wideners (not clip-contained):`);
  for (const o of res.out)
    console.log(`  off=${o.off} <${o.tag}${o.type ? '[' + o.type + ']' : ''}${o.testid ? ' #' + o.testid : ''}> kids=${o.kids} cls="${o.cls}"`);
  await ctx.close();
}
await browser.close();
