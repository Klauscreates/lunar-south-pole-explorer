// Run with PLAYWRIGHT_MODULE pointing to an installed Playwright ESM entry point.
// Tests the public UI and HTTP contracts; never bypasses scientific validation.
import assert from 'node:assert/strict';
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.APP_URL || 'http://127.0.0.1:3000';
const browser = await chromium.launch({channel:process.env.BROWSER_CHANNEL || 'chrome',headless:true});
const index = await (await fetch(`${base}/data/simulation-index.json`)).json();
const results=[];
function pass(name){results.push(name);console.log(`PASS ${name}`);}
try {
  for(const viewport of (process.env.FAULTS_ONLY ? [] : [{width:1440,height:1000},{width:390,height:844}].filter(v=>!process.env.ONLY_WIDTH || v.width===Number(process.env.ONLY_WIDTH)))) {
    const page = await browser.newPage({viewport});
    const errors=[];
    page.on('pageerror',e=>errors.push(String(e)));
    page.setDefaultTimeout(20000);
    await page.goto(base);
    await page.getByRole('button',{name:'Plan your mission',exact:true}).waitFor();
    assert.equal(await page.locator('.moon-dock').isVisible(),false);
    await page.getByRole('button',{name:'Plan your mission',exact:true}).click();await page.getByRole('button',{name:'See locations →',exact:true}).click();
    await page.locator('.location-row').last().waitFor();
    assert.equal(await page.locator('.location-row').count(),5);
    await page.locator('#location-browser .mission-methodology').first().locator('summary').click();
    assert.match(await page.locator('#location-browser').innerText(),/not RF signal strength/);
    await page.locator('#location-browser .mission-methodology').first().locator('summary').click();
    for(const site of index.sites) {
      console.log(`Checking ${viewport.width}px: ${site.name}`);
      await page.locator('.location-row').filter({hasText:site.name}).click();
      await page.getByRole('button',{name:'Expand location details'}).click();
      const card=page.locator('#selected-location-details');
      await card.getByText(/W modeled generation/).waitFor();
      assert.match(await card.innerText(),new RegExp(site.name));
      const date=card.locator('input[type="datetime-local"]');
      await date.fill('2026-10-04T12:00');
      assert.equal(await date.getAttribute('aria-invalid'),'false');
      await date.fill('2027-01-02T00:00');
      await card.getByRole('alert').waitFor();
      assert.match(await card.innerText(),/Unknown power/);
      assert.equal(await card.locator('.potential-grid').count(),0);
      await date.fill('2026-10-08T00:00');
      await card.getByText(/W modeled generation/).waitFor();
      await page.getByRole('button',{name:'Plan your mission',exact:true}).click();await page.getByRole('button',{name:'See locations →',exact:true}).click();
    }
    pass(`${viewport.width}px: all five sites, selection, dates, fail-closed results`);
    await page.getByRole('button',{name:'Close mission planner',exact:true}).click();
    await page.getByRole('button',{name:'◉ Sky · toward Earth',exact:true}).click();
    await page.locator('.sky-disclosure').waitFor();
    await page.getByRole('button',{name:'Moon overview',exact:true}).click();
    assert.equal(await page.locator('.sky-disclosure').count(),0);
    await page.getByRole('button',{name:'Plan your mission',exact:true}).click();await page.getByRole('button',{name:'See locations →',exact:true}).click();
    assert.equal(await page.locator('.orbit-launch').isVisible(),false);
    pass(`${viewport.width}px: sky view, globe reset and unobstructed location sheet`);
    await page.getByRole('button',{name:'Compare',exact:true}).click();
    await page.locator('.dual-site footer').nth(1).waitFor();
    assert.equal(await page.locator('.dual-pillar').count(),10);
    for(const site of index.sites.filter(s=>s.id!==index.sites.at(-1).id)) {
      await page.getByLabel('Comparison Target B').selectOption(site.id);
      await page.locator('.dual-site footer').nth(1).waitFor();
      assert.match(await page.locator('.dual-site').nth(1).innerText(),new RegExp(site.name));
    }
    await page.locator('.dual-configuration summary').click();
    const config=page.locator('.dual-dashboard').getByLabel('Study configuration');
    const options=await config.locator('option').evaluateAll(nodes=>nodes.map(n=>n.value));
    assert.equal(options.length,10);
    for(const option of options) {await config.selectOption(option); assert.equal(await page.locator('.dual-pillar').count(),10);}
    const date=page.locator('.dual-dashboard input[type="datetime-local"]');
    await date.fill('2026-09-30T00:00');
    assert.equal(await page.locator('.dual-site').count(),0);
    await date.fill('2026-10-01T00:00');
    await page.locator('.dual-site footer').first().waitFor();
    await page.getByRole('button',{name:'Next ten minutes'}).click();
    assert.equal(await page.locator('#dual-epoch').inputValue(),'1');
    await page.locator('#dual-epoch').fill('1008');
    assert.equal(await page.getByRole('button',{name:'Next ten minutes'}).isDisabled(),true);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.screenshot({path:`/tmp/lunar-compare-${viewport.width}.png`});
    pass(`${viewport.width}px: comparison targets, ten configurations, boundary epochs, no horizontal overflow`);
    await page.getByRole('button',{name:'Close mission planner',exact:true}).click();
    await page.getByRole('button',{name:'◌ Orbital view',exact:true}).click();
    await page.getByRole('button',{name:'Play orbital timeline'}).waitFor();
    const orbital=page.locator('.orbital-panel input[type="range"]');
    await orbital.fill('0');
    await page.getByRole('button',{name:'Play orbital timeline'}).click();
    await page.waitForFunction(()=>Number(document.querySelector('.orbital-panel input').value)>0);
    await page.getByRole('button',{name:'Pause orbital timeline'}).click();
    await page.screenshot({path:`/tmp/lunar-orbit-${viewport.width}.png`});
    await page.getByRole('button',{name:'Close orbital view'}).click();
    pass(`${viewport.width}px: orbital open, play, pause, close`);
    // Desktop instruments are separate from the mobile simplified explorer.
    if(viewport.width>1000) {
      await page.getByRole('button',{name:'Open scientific instruments'}).click();
      await page.getByLabel('GAUGE TERRAIN MODEL').selectOption('experimental');
      await page.getByRole('region',{name:'Experimental terrain gauges'}).waitFor();
      await page.getByLabel('GAUGE TERRAIN MODEL').selectOption('baseline');
      await page.getByLabel('PANEL ORIENTATION MODEL').selectOption({index:1});
      await page.getByRole('button',{name:'Spacecraft lab',exact:true}).click();
      await page.getByLabel('Body attitude').selectOption({index:1});
      await page.getByLabel('Assumed thermal environment').selectOption({index:1});
      await page.getByRole('button',{name:'Close spacecraft study'}).click();
      await page.getByRole('button',{name:'Native terrain',exact:true}).click();
      await page.getByRole('region',{name:'Native terrain study'}).waitFor();
      await page.getByRole('button',{name:'Close native terrain study'}).click();
      await page.getByRole('button',{name:'Data & methodology',exact:true}).click();
      await page.getByRole('link',{name:/Candidate coordinate source/}).waitFor();
      pass('desktop instruments: experimental/baseline gauges, power orientation, spacecraft and native terrain, provenance');
    } else {
      await page.getByRole('button',{name:'Open scientific instruments'}).click();
      await page.getByLabel('GAUGE TERRAIN MODEL').selectOption('experimental');
      await page.getByRole('region',{name:'Experimental terrain gauges'}).waitFor();
      await page.getByRole('button',{name:'Time',exact:true}).click();
      await page.getByLabel('Simulation timestamp').fill('500');
      await page.getByRole('button',{name:'Tools',exact:true}).click();
      await page.getByRole('button',{name:'Native terrain',exact:true}).click();
      await page.getByRole('region',{name:'Native terrain study'}).waitFor();
      await page.getByRole('button',{name:'Close native terrain study'}).click();
      pass('mobile instruments: gauge selection, time sheet and native terrain tools');
    }
    assert.deepEqual(errors,[]);
    pass(`${viewport.width}px: no uncaught browser errors`);
    await page.close();
  }
  for(const suffix of ['health','inspect?lon=0&lat=-89.9']) {
    const res=await fetch(`${base}/api/terrain/${suffix}`);assert.equal(res.status,200);assert.ok(await res.json());
  }
  assert.equal((await fetch(`${base}/api/terrain/forbidden`)).status,400);
  assert.equal((await fetch(`${base}/api/terrain/inspect?lon=0&lat=100`)).status,400);
  for(const layer of ['height','hillshade','slope','psr','height_error']) {
    const tile=await fetch(`${base}/api/terrain/${layer}/0/0/0`);
    assert.equal(tile.status,200);assert.ok((await tile.arrayBuffer()).byteLength>0);
  }
  pass('terrain proxy health, inspection and invalid route rejection');
  const page=await browser.newPage();
  await page.route('**/data/spacecraft/test-site-a.json',route=>route.fulfill({status:503,body:'Unavailable'}));
  await page.goto(base);await page.getByRole('button',{name:'Plan your mission',exact:true}).click();await page.getByRole('button',{name:'See locations →',exact:true}).click();
  await page.getByText('Some data unavailable; missing results are Unknown.').waitFor();
  assert.match(await page.locator('.location-row').first().innerText(),/Unknown energy/);
  pass('missing spacecraft study remains Unknown');
  await page.close();
  const badIndex = await browser.newPage();
  await badIndex.route('**/data/simulation-index.json',route=>route.fulfill({status:503,body:'Unavailable'}));
  await badIndex.goto(base);
  await badIndex.getByText(/Candidate simulation index unavailable/).waitFor();
  assert.equal(await badIndex.locator('.location-row').count(),0);
  pass('missing simulation index blocks predictions');
  await badIndex.close();
  const corrupt = await browser.newPage();
  await corrupt.route('**/data/spacecraft/test-site-a.json',async route=>{
    const response=await route.fetch();
    await route.fulfill({response,body:(await response.text())+' '});
  });
  await corrupt.goto(base);await corrupt.getByRole('button',{name:'Plan your mission',exact:true}).click();await corrupt.getByRole('button',{name:'See locations →',exact:true}).click();
  await corrupt.getByText('Some data unavailable; missing results are Unknown.').waitFor();
  assert.match(await corrupt.locator('.location-row').first().innerText(),/Unknown energy/);
  pass('corrupted checksum cannot produce a spacecraft prediction');
  // A failed shared request may be retried by another mounted panel. Let its
  // interception settle before closing the page, not after the browser is gone.
  await corrupt.unrouteAll({behavior:'wait'});
  await corrupt.close();
} finally {await browser.close();}
console.log(`Completed ${results.length} acceptance groups.`);
