// Browser QA against private offline pages rendered with the real Shared View.
// Usage: NODE_PATH=<playwright modules> node tests/shared_label_fit_qa.cjs <dir>
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const root=path.resolve(process.argv[2]);
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:1});
 await page.route(/^https?:/,r=>r.abort());
 const results=[];
 const measure=()=>({
  document:[document.documentElement.scrollWidth,document.documentElement.scrollHeight],
  graph:JSON.stringify(window.reviewSnapshot.state.graph),selection:window.reviewSnapshot.map.shared,
  cards:[...document.querySelectorAll('.topic-item')].map(card=>{
   const el=card.querySelector('.discussion-label'),r=document.createRange();r.selectNodeContents(el);
   const rects=[...r.getClientRects()].filter(r=>r.width>0),b=card.getBoundingClientRect();
   return {text:el.textContent,lines:new Set(rects.map(r=>Math.round(r.top))).size,font:parseFloat(getComputedStyle(card).fontSize),fit:card.dataset.textFit,
    position:[b.x,b.y,b.width,b.height],outside:rects.some(r=>r.top<b.top-1||r.bottom>b.bottom+1||r.left<b.left-1||r.right>b.right+1)};
  })
 });
 try{
  for(const name of ['canonical-fit','flow-fit','persistent-fit','extreme','generated-fit']){
   try{await fs.access(path.join(root,name+'.html'))}catch{continue}
   await page.goto('file://'+path.join(root,name+'.html')+'?viewport=1920x1080');
   await page.locator('.discussion-label').first().waitFor();
   await page.evaluate(()=>document.fonts.ready);await page.evaluate(()=>fitDiscussionCards());
   const first=await page.evaluate(measure);
   await page.evaluate(()=>fitDiscussionCards());assert.deepEqual(await page.evaluate(measure),first,'Repeated fitting must be stable');
   assert.equal(first.cards.length,6);
   assert.ok(first.cards.every(c=>[40,38,36].includes(c.font)));
   if(name==='extreme'){
    assert.equal(first.cards[0].fit,'unresolved');assert.equal(first.cards[0].font,36);
    assert.ok(first.cards[0].text.length>300,'No truncation');
   }else{
    assert.deepEqual(first.document,[1920,1080]);
    assert.ok(first.cards.every(c=>c.lines<=5&&!c.outside&&c.fit==='fit'),name+' text must fit');
   }
   if(name==='persistent-fit'){
    const rail=await page.locator('.persistent-rail').innerText();assert.ok(rail.includes('山田さん')&&rail.includes('2026-09-26'));
   }
   await page.screenshot({path:path.join(root,name+'.png')});
   // Re-render/resize cannot change labels, selection or slot positions.
   await page.evaluate(()=>renderShared(window.reviewSnapshot,true));assert.deepEqual(await page.evaluate(measure),first);
   results.push({name,browser:browser.version(),...first});
   console.log(name,JSON.stringify(first.cards.map(c=>({lines:c.lines,font:c.font,fit:c.fit}))));
  }
  await fs.writeFile(path.join(root,'pixel-metrics.json'),JSON.stringify(results.map(({graph,...r})=>r),null,2));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
