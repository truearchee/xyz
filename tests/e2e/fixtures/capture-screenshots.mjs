#!/usr/bin/env node
// Stage 4.9e close-out — design-match EVIDENCE capture (NOT a gate; the design-match SIGN-OFF is the
// developer's human step). Logs in as each seeded role, visits every restyled §5 surface at desktop (1280)
// and mobile (375), writes PNGs to knowledge/steps/stage-04/4.9-design-review/, and asserts NO horizontal
// scroll at 375 (the 4.9 mobile sanity target). A `.mjs` (not `*.spec.ts`) so run-active-suite.sh never
// picks it up. Prereq: e2e stack up + `node tests/e2e/fixtures/seed.mjs` already run this session.
import { chromium } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const BASE = process.env.E2E_BASE_URL ?? 'http://localhost:3000';
const PASSWORD = process.env.E2E_TEST_PASSWORD ?? 'LocalE2EPassword123!';
const OUT = resolve(process.cwd(), 'knowledge/steps/stage-04/4.9-design-review');
const MODULE = '20000000-0000-4000-8000-000000000001';
const SECTION = '40000000-0000-4000-8000-000000000002';
const VIEWPORTS = [
  { tag: 'desktop', width: 1280, height: 800 },
  { tag: 'mobile', width: 375, height: 812 },
];

const USERS = {
  admin: { email: 'admin_e2e@example.test', home: '/admin' },
  lecturer: { email: 'lecturer_e2e@example.test', home: '/lecturer' },
  student: { email: 'student_e2e@example.test', home: '/student' },
};

// Named restyled surfaces (4.9c inventory): role → [route, slug]
const SURFACES = {
  _public: [['/login', 'login']],
  admin: [['/admin', 'admin-dashboard'], ['/unauthorized', 'access-denied']],
  lecturer: [['/lecturer', 'lecturer-home'], [`/lecturer/modules/${MODULE}`, 'lecturer-module-detail']],
  student: [
    ['/student', 'student-home'],
    [`/student/modules/${MODULE}`, 'student-module-detail'],
    [`/student/modules/${MODULE}/sections/${SECTION}`, 'student-section-detail'],
  ],
};

async function signIn(page, email, home) {
  await page.goto(`${BASE}/login`);
  await page.waitForFunction(() => typeof window.__xyzE2E !== 'undefined');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.waitForURL(new RegExp(`${home}$`));
  await page.waitForFunction(() => typeof window.__xyzE2E !== 'undefined');
}

async function shoot(page, route, slug, vp, scrollReport) {
  await page.setViewportSize({ width: vp.width, height: vp.height });
  await page.goto(`${BASE}${route}`);
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.waitForTimeout(400); // let fonts/animations settle
  const file = `${slug}.${vp.tag}.png`;
  await page.screenshot({ path: resolve(OUT, file), fullPage: true });
  if (vp.tag === 'mobile') {
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    scrollReport.push({ route, overflowPx: overflow, ok: overflow <= 1 });
  }
  console.log(`  shot ${file}`);
}

async function main() {
  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const scrollReport = [];
  try {
    // public (no auth)
    {
      const ctx = await browser.newContext();
      const page = await ctx.newPage();
      for (const [route, slug] of SURFACES._public)
        for (const vp of VIEWPORTS) await shoot(page, route, slug, vp, scrollReport);
      await ctx.close();
    }
    // per-role
    for (const [role, u] of Object.entries(USERS)) {
      console.log(`[${role}]`);
      const ctx = await browser.newContext();
      const page = await ctx.newPage();
      await signIn(page, u.email, u.home);
      for (const [route, slug] of SURFACES[role])
        for (const vp of VIEWPORTS) await shoot(page, route, slug, vp, scrollReport);
      await ctx.close();
    }
  } finally {
    await browser.close();
  }

  const failures = scrollReport.filter((r) => !r.ok);
  writeFileSync(
    resolve(OUT, 'mobile-sanity.json'),
    JSON.stringify({ target: '375px, no horizontal scroll (overflow <= 1px)', checks: scrollReport }, null, 2),
  );
  console.log('\n== mobile sanity (375px) ==');
  for (const r of scrollReport) console.log(`  ${r.ok ? 'OK ' : 'FAIL'} ${r.route} overflow=${r.overflowPx}px`);
  if (failures.length) {
    console.error(`\nMOBILE SANITY FAILED: ${failures.length} surface(s) scroll horizontally at 375px`);
    process.exit(1);
  }
  console.log('\nALL surfaces captured; mobile sanity PASS (no horizontal scroll at 375px).');
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
