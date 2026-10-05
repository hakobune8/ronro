// Browser pixel QA of the loopback Product server. No audio or remote pages.
const {chromium}=require('playwright');
const fs=require('node:fs/promises');
const path=require('node:path');
(async()=>{
  const out=process.argv[2]; if(!out)throw Error('Private output directory required');
  await fs.mkdir(out,{recursive:false});
  const browser=await chromium.launch({headless:true});
  const context=await browser.newContext({viewport:{width:1920,height:1080},deviceScaleFactor:1});
  const page=await context.newPage();
  const results=[];
  try {
    for(const name of ['t1-5','t1-10','t1-15','persistent-1','persistent-3','persistent-9','persistent-flow']){
      await page.goto(`http://127.0.0.1:18884/shared?fixture=${name}&viewport=1920x1080`);
      await page.locator('.current-discussion .topic-item').first().waitFor();
      await page.evaluate(()=>document.fonts.ready);
      const metrics=await page.evaluate(()=>{
        const selectors=['.topic-item','.persistent-item','.persistent-section','.persistent-rail','.flow-list','.flow-item','.shared-status','.topic-more'];
        const elements=selectors.flatMap(s=>[...document.querySelectorAll(s)].filter(e=>e.getClientRects().length).map(e=>{
          const r=e.getBoundingClientRect(),style=getComputedStyle(e),range=document.createRange();range.selectNodeContents(e);
          const text=range.getBoundingClientRect();
          return {selector:s,text:e.textContent,rect:{x:r.x,y:r.y,width:r.width,height:r.height,bottom:r.bottom,right:r.right},font:style.fontSize,lineHeight:style.lineHeight,
            overflowX:e.scrollWidth>e.clientWidth+1,overflowY:e.scrollHeight>e.clientHeight+1,
            textOutside:text.width>0&&(text.left<r.left-1||text.right>r.right+1||text.top<r.top-1||text.bottom>r.bottom+1)};
        }));
        const visible=e=>e&&e.getClientRects().length>0;
        return {viewport:[innerWidth,innerHeight],document:[document.documentElement.scrollWidth,document.documentElement.scrollHeight],
          dpr:devicePixelRatio,elements,visibleBrand:visible(document.querySelector('.brand')),visibleGuide:visible(document.querySelector('.shared-footer')),
          controls:[...document.querySelectorAll('a,button,input,select')].filter(visible).length,
          cardLabels:[...document.querySelectorAll('.topic-item')].map(e=>e.textContent),
          overflow:[...document.querySelectorAll('.topic-more')].filter(visible).map(e=>e.textContent),
          flowVisible:visible(document.querySelector('.flow-band'))};
      });
      const bytes=await page.screenshot({path:path.join(out,name+'.png'),fullPage:false});
      if(bytes.readUInt32BE(16)!==1920||bytes.readUInt32BE(20)!==1080)throw Error('Screenshot dimensions incorrect');
      results.push({name,browser:browser.version(),...metrics});
      console.log(name,JSON.stringify({document:metrics.document,rail:metrics.elements.filter(e=>e.selector==='.persistent-section').length,issues:metrics.elements.filter(e=>e.overflowX||e.overflowY||e.textOutside).map(e=>e.selector)}));
    }
    await fs.writeFile(path.join(out,'pixel-metrics.json'),JSON.stringify(results,null,2));
  } finally {await browser.close();}
})().catch(e=>{console.error(e.message);process.exitCode=1;});
