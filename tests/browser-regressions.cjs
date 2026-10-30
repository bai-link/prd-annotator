// Optional browser QA: npm install --no-save playwright; npx playwright install chromium
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('fs'),os=require('os'),path=require('path'),assert=require('assert/strict'),{execFileSync}=require('child_process');
(async()=>{
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'prd-annotator-')),root=path.resolve(__dirname,'..');
 const src=path.join(tmp,'source.html'),out=path.join(tmp,'annotated.html'),notes=path.join(tmp,'notes.json');
 fs.writeFileSync(src,`<html><body><style>.clip{overflow:hidden;width:200px;height:70px;border:1px solid}#action{width:180px;height:35px}#modal{position:fixed;inset:100px;background:white;z-index:81}.modal:not(.on){display:none}.mask{position:fixed;inset:0;z-index:80;background:#0008}.mask:not(.on){display:none}</style>
 <h1 id="title">业务工作台</h1><div class="clip"><button id="action" onclick="this.dataset.called='yes'">保存业务</button></div><p id="rule">复议仅一次</p><p id="feedback" role="alert">资料不足，请补充</p>
 <div class="mask" id="mask"></div><section id="modal" class="modal" role="dialog" aria-modal="true"><h2 id="modalTitle">当前弹窗</h2><button id="close" onclick="document.querySelector('#modal').classList.remove('on');document.querySelector('#mask').classList.remove('on')">关闭</button></section></body></html>`);
 fs.writeFileSync(notes,JSON.stringify({meta:{schema:1},notes:[
  {anchor:'custom:title',kind:'custom',css:'#title',title:'业务工作台',func:'整体用途',status:'confirmed'},
  {anchor:'custom:action',kind:'custom',css:'#action',title:'保存业务',rules:['保存校验'],status:'confirmed',replaces:[{css:'#rule',text:'复议仅一次'},{css:'#feedback',text:'资料不足，请补充'}]},
  {anchor:'custom:modal',kind:'custom',css:'#modalTitle',title:'当前弹窗',func:'弹窗规则',status:'confirmed'},
  {anchor:'custom:excluded',kind:'custom',css:'#feedback',title:'非需求',status:'n/a'}]}));
 execFileSync(process.env.PYTHON||'python',['-X','utf8',path.join(root,'scripts/prd_notes.py'),'inject',src,'--notes',notes,'-o',out]);
 const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{})});
 try{
  const page=await browser.newPage({viewport:{width:900,height:700}}),errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto(require('url').pathToFileURL(out).href);
  const badge=a=>page.locator('.prd-badge[data-a="custom:'+a+'"]');await badge('action').waitFor();
  assert.equal(await page.locator('#action .prd-badge').count(),0,'never mutate business children');assert.equal(await page.locator('#rule').isVisible(),false);assert.equal(await page.locator('#feedback').isVisible(),true);
  assert.equal(await badge('excluded').count(),0);const r=await badge('action').boundingBox();assert.ok(r.width===16&&r.y>=0&&r.x>=0);await badge('action').click();assert.match(await page.locator('.prd-pop').innerText(),/保存校验/);assert.equal(await page.locator('#action').getAttribute('data-called'),null);await page.keyboard.press('Escape');
  await page.locator('#action').click();assert.equal(await page.locator('#action').getAttribute('data-called'),'yes');
  await page.evaluate(()=>{document.querySelector('#modal').classList.add('on');document.querySelector('#mask').classList.add('on')});await badge('modal').waitFor();assert.equal(await badge('action').isVisible(),false);assert.equal(await page.locator('.prd-fabs').isVisible(),false);await badge('modal').click();assert.match(await page.locator('.prd-pop').innerText(),/弹窗规则/);await page.keyboard.press('Escape');await page.locator('#close').click();await badge('action').waitFor();assert.equal(await page.locator('.prd-fabs').isVisible(),true);
  await page.evaluate(()=>document.querySelector('#action').outerHTML='<button id="action">重渲染后的保存</button>');await page.waitForFunction(()=>window.__PRD_ANNOTATION_AUDIT__.some(x=>x.anchor==='custom:action'&&x.result==='matched'));await badge('action').click();assert.match(await page.locator('.prd-pop').innerText(),/保存业务/);assert.deepEqual(errors,[]);
  console.log('PASS clipping, overlay scope, toolbar, immutable host structure, rule replacement safeguards, n/a exclusion, rerender');
 }finally{await browser.close();fs.rmSync(tmp,{recursive:true,force:true})}
})().catch(e=>{console.error(e);process.exit(1)});
