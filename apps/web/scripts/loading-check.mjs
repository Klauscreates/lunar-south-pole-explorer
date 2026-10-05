// Repeatable browser-side loading check. Cold browser cache, warm/cold host as found.
import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const browser=await chromium.launch({channel:'chrome',headless:true});
try {
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  page.setDefaultTimeout(60000);
  const requests=[];
  page.on('request',request=>requests.push(new URL(request.url()).pathname));
  const started=Date.now();
  await page.goto(process.env.APP_URL || 'http://127.0.0.1:3000');
  await page.getByRole('button',{name:'Locations',exact:true}).waitFor();
  const controlsMs=Date.now()-started;
  await page.locator('canvas').first().waitFor();
  // Allow speculative startup requests to appear before opening Locations.
  await page.waitForTimeout(3000);
  const startupCandidates=requests.filter(p=>/^\/data\/(connecting-ridge|haworth|malapert-massif|nobile-rim-1)\.json$/.test(p)).length;
  await page.getByRole('button',{name:'Locations',exact:true}).click();
  await page.waitForFunction(()=>!document.querySelector('#location-browser')?.textContent.includes('Verifying all five'));
  const before=requests.filter(p=>/^\/data\/spacecraft\/(?!index|component-spec)[^/]+\.json$/.test(p)).length;
  await page.getByRole('button',{name:'Close locations',exact:true}).click();
  await page.getByRole('button',{name:'Locations',exact:true}).click();
  await page.waitForTimeout(1000);
  const repeatStudyRequests=requests.filter(p=>/^\/data\/spacecraft\/(?!index|component-spec)[^/]+\.json$/.test(p)).length-before;
  console.log(JSON.stringify({url:process.env.APP_URL || 'local',controlsMs,startupCandidates,repeatStudyRequests},null,2));
  if(process.env.EXPECT_OPTIMIZED){assert.equal(startupCandidates,0);assert.equal(repeatStudyRequests,0);}
} finally {await browser.close();}
