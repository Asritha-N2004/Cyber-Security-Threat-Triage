import { test,expect } from '@playwright/test';

test('local dashboard opens and switches demo identity without credentials',async({page,request})=>{
 const mode=await (await request.get('/api/v1/auth/mode')).json();
 test.skip(mode.mode!=='local_demo','Run against the explicitly enabled local demo server.');
 await page.goto('/');
 await expect(page.getByRole('heading',{name:'A clearer view of your books.'})).toBeVisible();
 await expect(page.getByLabel('Access token')).toHaveCount(0);
 const administrator=mode.users.find((user:{name:string;role:string})=>user.name==='administrator');
 await page.getByLabel('Local demo identity').selectOption(administrator.id);
 await page.getByRole('link',{name:'Accounting controls',exact:true}).click();
 await expect(page.getByRole('button',{name:'Save policy'})).toBeEnabled();
 await page.setViewportSize({width:390,height:844});
 await expect(page.getByLabel('Local demo identity')).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
});
