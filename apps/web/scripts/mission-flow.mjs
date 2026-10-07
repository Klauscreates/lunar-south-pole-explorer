import assert from 'node:assert/strict';
import {weeklyMetrics} from '../components/weeklyMetrics.ts';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base=process.env.APP_URL || 'http://127.0.0.1:3000';
const browser=await chromium.launch({channel:'chrome',headless:true});
try {
 for(const width of [390,1440]) {
  const page=await browser.newPage({viewport:{width,height:900}});
  page.setDefaultTimeout(60000);const errors=[];page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(base);
  await page.getByRole('button',{name:'Plan your mission',exact:true}).click();
  await page.getByRole('heading',{name:'Pick your dates.'}).waitFor();
  assert.equal(await page.locator('.location-row').count(),0);
  await page.getByLabel('Mission start · UTC').fill('2026-10-02T00:00');
  await page.getByLabel('Mission end · UTC').fill('2026-12-31T00:00');
  assert.equal(await page.getByRole('button',{name:'See locations →'}).isEnabled(),false);
  await page.locator('.mission-date-selection').getByRole('alert').waitFor();
  await page.getByLabel('Mission end · UTC').fill('2026-10-03T00:00');
  await page.screenshot({path:`/tmp/mission-dates-${width}.png`});
  await page.getByRole('button',{name:'See locations →'}).click();
  await page.locator('.location-row').first().getByText(/kWh/).waitFor();
  const study=await (await fetch(`${base}/data/spacecraft/test-site-a.json`)).json();
  const totals=weeklyMetrics(study,'north--low_load',144,288);
  assert.match(await page.locator('.location-row').first().innerText(),new RegExp(`${totals.kwh.toFixed(2)} kWh`));
  assert.match(await page.locator('.location-row').first().innerText(),new RegExp(`${totals.commsPercent.toFixed(1)}% LOS`));
  await page.screenshot({path:`/tmp/mission-locations-${width}.png`});
  await page.locator('.location-row').first().click();
  await page.getByRole('button',{name:'Expand location details'}).click();
  await page.getByRole('button',{name:'Compare this location'}).click();
  await page.locator('.dual-site footer').nth(1).waitFor();
  assert.equal(await page.locator('#dual-epoch').getAttribute('min'),'144');
  assert.equal(await page.locator('#dual-epoch').getAttribute('max'),'288');
  assert.match(await page.locator('.dual-site').first().innerText(),/Selected window:/);
  await page.getByLabel('Comparison Target B').selectOption('haworth');
  await page.locator('.dual-site').nth(1).getByRole('heading',{name:'Haworth',exact:true}).waitFor();
  assert.deepEqual(errors,[]);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  console.log(`PASS ${width}px date-first mission flow, unsupported dates, interval totals and comparison window`);
  await page.close();
 }
} finally {await browser.close();}
