import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
// Requires initialized, running backend. Credentials never enter source control.
test('synthetic reconciliation and investigation',async({page})=>{
  const credentials=JSON.parse(readFileSync('../backend/.local/credentials.json','utf8'));
  await page.goto('/');
  await page.getByLabel('Access token').fill(credentials.analyst);
  await page.getByRole('button',{name:'Enter workspace'}).click();
  await expect(page.getByText('A clearer view of your books.')).toBeVisible();
  await page.getByRole('button',{name:'Run synthetic demo'}).click();
  await expect(page.getByText('Matching explorer')).toBeVisible();
  await page.getByRole('link',{name:/Investigate/}).first().click();
  await page.getByRole('button',{name:'Investigate exception'}).click();
  await expect(page.getByRole('heading',{name:'Correction recommendation',exact:true})).toBeVisible();
  await expect(page.getByText('Validation passed',{exact:true})).toBeVisible();
  await page.screenshot({path:'../docs/screenshots/investigation.png',fullPage:true});
  await page.getByRole('link',{name:'Overview',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Recent reconciliations'})).toBeVisible();
  await page.screenshot({path:'../docs/screenshots/dashboard.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await expect(page.getByRole('heading',{name:'A clearer view of your books.'})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
  await page.screenshot({path:'../docs/screenshots/mobile.png',fullPage:true});
});
