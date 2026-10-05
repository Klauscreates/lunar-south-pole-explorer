// Chromium touch emulation, not physical iPhone/Safari qualification.
import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const browser=await chromium.launch({channel:'chrome',headless:true});
try {
  const context=await browser.newContext({viewport:{width:390,height:844},hasTouch:true,isMobile:true});
  const page=await context.newPage(); const errors=[];
  page.on('pageerror',error=>errors.push(String(error)));
  page.setDefaultTimeout(60000);
  const cdp=await context.newCDPSession(page);
  const touch=(type,points)=>cdp.send('Input.dispatchTouchEvent',{type,touchPoints:points.map(([id,x,y])=>({id,x,y}))});
  async function drag(dx,dy) {
    await touch('touchStart',[[1,195,420]]);
    for(let i=1;i<=12;i++) {await touch('touchMove',[[1,195+dx*i/12,420+dy*i/12]]);await page.waitForTimeout(16);}
    await touch('touchEnd',[]); await page.waitForTimeout(400);
  }
  await page.goto(process.env.APP_URL || 'http://127.0.0.1:3000');
  await page.getByRole('button',{name:'Locations',exact:true}).waitFor();
  await page.locator('canvas').first().waitFor(); await page.waitForTimeout(2500);
  for(const delta of [[70,0],[-70,0],[0,70],[0,-70]]) await drag(...delta);
  await page.getByRole('button',{name:'↻ Look 360°',exact:true}).click();
  for(let i=0;i<12;i++) await drag(140,0);
  for(const delta of [[0,100],[0,-100]]) await drag(...delta);
  await page.getByRole('button',{name:'↔ Pan',exact:true}).click();
  console.log('PASS surface touch drags in four directions without renderer failure');
  await page.getByRole('button',{name:'◌ Orbital view',exact:true}).click();
  await page.getByRole('button',{name:'Play orbital timeline'}).waitFor(); await page.waitForTimeout(2000);
  const before=await page.screenshot({path:'/tmp/lunar-touch-before.png'});
  await drag(75,0);
  const after=await page.screenshot({path:'/tmp/lunar-touch-after.png'});
  assert.notDeepEqual(before,after);
  for(const delta of [[-75,0],[0,60],[0,-60]]) await drag(...delta);
  await page.getByRole('button',{name:'↻ Look 360°',exact:true}).click();
  for(let i=0;i<12;i++) await drag(140,0);
  for(const delta of [[0,100],[0,-100]]) await drag(...delta);
  await page.getByRole('button',{name:'↔ Pan',exact:true}).click();
  await touch('touchStart',[[1,155,420],[2,235,420]]);
  for(let i=1;i<=10;i++){await touch('touchMove',[[1,155-i*3,420],[2,235+i*3,420]]);await page.waitForTimeout(16);}
  await touch('touchEnd',[]);
  await page.getByRole('button',{name:'Close orbital view'}).click();
  await drag(30,0);
  await page.getByRole('button',{name:'Locations',exact:true}).click();
  assert.equal(await page.locator('.location-row').count(),5);
  assert.deepEqual(errors,[]);
  console.log('PASS orbital pan changes rendered scene; four directions, pinch, exit and controls remain functional');
} finally {await browser.close();}
