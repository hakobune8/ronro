// Offline visual QA for a generated PRIVATE discussion-projection HTML file.
const fs = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require('playwright');

async function main() {
  const input = path.resolve(process.argv[2]);
  const output = path.dirname(input);
  const browser = await chromium.launch({headless: true});
  const page = await browser.newPage({viewport: {width: 1920, height: 1080}, deviceScaleFactor: 1});
  await page.route(/^https?:/, route => route.abort());
  const rows = [];
  try {
    const cases = [
      ['t1-5','grid'],['t1-5','flow'],['t1-5','detail'],
      ['t1-10','grid'],['t1-10','flow'],['t1-10','detail'],
      ['t1-15','grid'],['t1-15','flow'],['t1-15','detail'],
      ['t2-short','grid'],['t2-short','flow'],['t2-short','detail'],
      ['final-t1','final'],['t2-short','final'],
    ];
    for (const [dataset, mode] of cases) {
      await page.goto(`file://${input}?dataset=${dataset}&mode=${mode}`);
      await page.evaluate(() => document.fonts.ready);
      const result = await page.evaluate(() => {
        const el = document.getElementById('stage');
        const base = el.getBoundingClientRect();
        const boxes = [...el.querySelectorAll('.flow-card,.latest-detail,.grid-card,.rail-item')].map(x => {
          const r = x.getBoundingClientRect();
          return {kind: x.className, textLength: x.textContent.length,
            clipped: x.scrollHeight > x.clientHeight + 2 || x.scrollWidth > x.clientWidth + 2,
            outside: r.left < base.left - 1 || r.right > base.right + 1 || r.top < base.top - 1 || r.bottom > base.bottom + 1};
        });
        return {size: [Math.round(base.width), Math.round(base.height)],
          boxes, clipped: boxes.filter(x => x.clipped).length,
          outside: boxes.filter(x => x.outside).length};
      });
      await page.locator('#stage').screenshot({path: path.join(output, `${dataset}-${mode}.png`)});
      rows.push({dataset, mode, ...result});
      console.log(`${dataset}-${mode}: ${result.size.join('x')}, clipped=${result.clipped}, outside=${result.outside}`);
    }
    await fs.writeFile(path.join(output,'visual-qa.json'), JSON.stringify({browser: browser.version(),viewport:[1920,1080],rows},null,2));
  } finally { await browser.close(); }
}
main().catch(err => {console.error(err);process.exitCode=1});
