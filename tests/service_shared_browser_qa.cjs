// Synthetic browser acceptance for the Account Service -> existing Semantic Canvas bridge.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const html = fs.readFileSync(path.join(__dirname, '../prototype/web/shared.html'), 'utf8');
const nodes = [
  {id:'issue',x:0,y:0,type:'concern',status:'active',label:'飲料水が不足',canonical:'三避難所で初日の飲料水が不足している。',time_at:'2026-10-06T00:02:00Z',root_state:'unconfirmed',created_sequence:2,activity_sequence:2},
  {id:'option',x:0,y:260,type:'option',status:'active',label:'倉庫の水を再配置',canonical:'既存倉庫の水を三避難所に再配置する案を検討する。',time_at:'2026-10-06T00:05:00Z',root_state:'linked',created_sequence:3,activity_sequence:3},
  {id:'reason',x:-430,y:260,type:'idea',status:'active',label:'再配置なら早い',canonical:'倉庫内の在庫を使えば初日に間に合う見込み。',time_at:'2026-10-06T00:08:00Z',root_state:'unconfirmed',created_sequence:4,activity_sequence:4},
];
const canvas = {
  version:'semantic-canvas-v1',session_id:'synthetic-session',session_title:'合成の検討会',revision:4,
  nodes,edges:[
    {id:'e1',source_node_id:'issue',target_node_id:'option',type:'discussion_provenance'},
    {id:'e2',source_node_id:'reason',target_node_id:'option',type:'supports'},
  ],focus_id:'option',near_ids:['issue','option','reason'],latest_detail_id:'option',
  live_camera:{x:0,y:160,scale:.86,focus_id:'option'},
  final_camera:{x:-215,y:130,scale:.6},root_ids:[],unconfirmed_ids:['issue','reason'],
};

async function main() {
  let state = 'open';
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1920,height:1080}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.pathname === '/shared') return route.fulfill({status:200,contentType:'text/html',body:html});
      if (url.pathname.endsWith('/canvas')) return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(canvas)});
      if (url.pathname.endsWith('/synthetic-session')) return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({state,capture_state:state==='open'?'listening':state,graph_revision:canvas.revision})});
      return route.fulfill({status:404,body:'not found'});
    });
    await page.goto('https://ronro.example.test/shared?service=1#session=synthetic-session');
    await page.locator('.canvas-node').first().waitFor();
    assert.equal(await page.locator('.canvas-node').count(),3);
    assert.equal(await page.locator('.canvas-node.focus').count(),1);
    assert.equal(await page.locator('.canvas-edge.provenance').count(),1);
    assert.equal(await page.locator('.canvas-edge.supports').count(),1);
    assert.match(await page.locator('.canvas-detail').innerText(), /既存倉庫の水を三避難所に再配置する案/);
    assert.match(await page.locator('#canvas-session-title').innerText(), /合成の検討会/);
    assert.equal(await page.locator('#canvas-counts').isVisible(),true);
    state = 'ended';
    canvas.revision += 1;
    await page.evaluate(() => refresh());
    await page.locator('.canvas-final-marker').first().waitFor();
    assert.equal(await page.locator('.canvas-node').count(),0);
    assert.equal(await page.locator('.canvas-detail').count(),0);
    assert.equal(await page.locator('.canvas-final-marker').count(),3);
    state = 'ended_incomplete';
    canvas.revision += 1;
    await page.evaluate(() => refresh());
    assert.match(await page.locator('.canvas-final-note').innerText(), /記録できなかった可能性/);
    assert.deepEqual(errors,[]);
    console.log('service shared live/final browser QA: PASS');
  } finally { await browser.close(); }
}

main().catch(error => { console.error(error); process.exitCode=1; });
