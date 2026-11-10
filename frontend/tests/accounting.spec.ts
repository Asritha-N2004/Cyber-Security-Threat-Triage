import { test,expect,type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
const credentials=JSON.parse(readFileSync('../backend/.local/credentials.json','utf8'));
async function login(page:Page,name='analyst') {
 await page.goto('/');
 await page.getByLabel('Access token').fill(credentials[name]);
 await page.getByRole('button',{name:'Enter workspace'}).click();
 await expect(page.getByRole('heading',{name:'A clearer view of your books.'})).toBeVisible();
}

test('AP workflow, matching review and PDF report',async({page})=>{
 await login(page);
 await page.getByRole('link',{name:'Accounting workflows',exact:true}).click();
 await page.getByRole('button',{name:'Run AP synthetic demo',exact:true}).click();
 await expect(page.getByText('partial payment',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Compare records'}).first().click();
 await page.getByPlaceholder('Explain your decision (8 characters minimum)').fill('Verified synthetic invoice and payments against purchase order');
 await page.getByRole('button',{name:'Record review',exact:true}).click();
 await expect(page.getByText('Review recorded in the audit history.')).toBeVisible();
 await page.getByRole('link',{name:'Financial reports',exact:true}).click();
 const downloaded=page.waitForEvent('download');
 await page.getByRole('button',{name:'PDF',exact:true}).first().click();
 expect((await downloaded).suggestedFilename()).toMatch(/\.pdf$/);
 await page.screenshot({path:'../docs/screenshots/reports-updated.png',fullPage:true});
});

test('fee proposal, independent approval, simulation and reversal',async({page})=>{
 await login(page);
 await page.getByRole('button',{name:'Run synthetic demo'}).click();
 const feeRow=page.getByRole('row').filter({hasText:'USD 25.00'});
 await feeRow.getByRole('link',{name:/Investigate/}).click();
 const response=page.waitForResponse(r=>r.url().endsWith('/investigate')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'Investigate exception',exact:true}).click();
 const proposal=await (await response).json();
 await expect(page.getByText('Validation passed',{exact:true})).toBeVisible();
 await page.locator('.user-menu').click();
 await login(page,'checker');
 await page.getByRole('link',{name:'Approval center',exact:true}).click();
 const card=page.locator('section.panel').filter({hasText:`PROPOSAL ${proposal.id.slice(0,8).toUpperCase()}`});
 await card.getByRole('button',{name:'Approve draft'}).click();
 await card.getByRole('button',{name:'Simulate adjustment'}).click();
 await expect(card.getByText('executed',{exact:true})).toBeVisible();
 await card.getByRole('button',{name:'Create reversal'}).click();
 await expect(card.getByText('reversed',{exact:true})).toBeVisible();
});

test('CSV preview, saved mapping and partial validation',async({page})=>{
 await login(page);
 await page.getByRole('link',{name:'Data imports',exact:true}).click();
 await page.getByLabel('Financial data file').setInputFiles({name:'browser-bank.csv',mimeType:'text/csv',buffer:Buffer.from('transaction_id,date,account,currency,amount\nBROWSER-1,2026-01-01,cash,USD,12.30\nBAD,invalid,cash,USD,1\n')});
 await page.getByRole('button',{name:'Preview first 20 records'}).click();
 await expect(page.getByText('Validation preview · no records imported')).toBeVisible();
 await page.getByPlaceholder('e.g. Monthly bank export').fill(`Browser mapping ${Date.now()}`);
 await page.getByRole('button',{name:'Save mapping',exact:true}).click();
 await page.getByRole('button',{name:'Validate and import',exact:true}).click();
 await expect(page.getByRole('heading',{name:'browser-bank.csv'})).toBeVisible();
 await expect(page.getByText('Rejected records remain in the validation report with the original values and an explanation.')).toBeVisible();
 await expect(page.getByRole('button',{name:'Download validation errors'})).toBeVisible();
});

test('durable queued investigation displays all ten agents',async({page})=>{
 await login(page);
 await page.getByRole('link',{name:'Accounting workflows',exact:true}).click();
 await page.getByRole('button',{name:'Run AR synthetic demo',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Matching explorer',exact:true})).toBeVisible();
 await page.getByRole('link',{name:'Agent observatory',exact:true}).click();
 await page.getByRole('button',{name:'Queue investigation',exact:true}).click();
 await expect(page.getByText(/Task: completed/)).toBeVisible({timeout:20000});
 await page.getByRole('button',{name:'Refresh',exact:true}).click();
 await expect(page.getByText('Data quality',{exact:true})).toBeVisible();
 await expect(page.getByText('Transaction matching',{exact:true})).toBeVisible();
 await expect(page.getByText('Decision explanation',{exact:true})).toBeVisible();
 expect(await page.locator('.agent-finding').count()).toBe(10);
 await page.screenshot({path:'../docs/screenshots/ten-agent-observatory.png',fullPage:true});
});
