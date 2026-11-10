// Paired live acceptance over the actual daemon wire; never launches Chrome or sends a post.
import assert from 'node:assert/strict';
import {createConnection} from 'node:net';
import {execFileSync} from 'node:child_process';
import {mkdirSync, writeFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {performance} from 'node:perf_hooks';
import {DAEMON_RUNTIME_VERSION} from '../src/browser_cli/task_runtime/node/client.mjs';

const output = resolve(process.argv[2]);
const samples = Number(process.argv[3] || 3);
assert.ok(Number.isInteger(samples) && samples > 0);
const status = JSON.parse(execFileSync('browser-cli', ['status', '--json'], {encoding:'utf8'}));
assert.equal(status.data.health.extension.connected, true);
const socketPath = JSON.parse(execFileSync('browser-cli', ['paths', '--json'], {encoding:'utf8'})).data.socket_path;
let sequence = 0;
const traffic = [];
const rows = [];
async function request(action, args = {}, measured = false) {
  const body = JSON.stringify({action, args, agent_id:'input-acceptance',
    request_id:`input-${String(++sequence).padStart(5,'0')}`, runtime_version:DAEMON_RUNTIME_VERSION})+'\n';
  const start = performance.now();
  const raw = await new Promise((resolve, reject) => {
    const socket = createConnection(socketPath);
    const chunks = [];
    socket.setTimeout(30000, () => socket.destroy(new Error('Acceptance request timed out; not replayed')));
    socket.on('connect', () => socket.end(body));
    socket.on('data', chunk => {chunks.push(chunk); if(chunk.includes(10)) {resolve(Buffer.concat(chunks)); socket.destroy();}});
    socket.on('error', reject);
    socket.on('end', () => {if(!chunks.length) reject(new Error('Disconnected; not replayed'));});
  });
  const response = JSON.parse(raw.toString());
  const record = {action, request_bytes:Buffer.byteLength(body), response_bytes:raw.length,
    ms:performance.now()-start, measured};
  traffic.push(record);
  assert.equal(response.ok, true, JSON.stringify(response));
  return {data:response.data, record};
}
const evaluate = async code => (await request('eval', {code})).data.result;
const setupSearch = `() => {const el=document.querySelector('input[aria-label="查询词条"], input[data-testid="SearchBox_Search_Input"]'); if(!el)throw Error('Search field missing'); el.value=''; el.blur(); return true;}`;
const searchState = `() => {const el=document.querySelector('input[aria-label="查询词条"], input[data-testid="SearchBox_Search_Input"]');return {focused:document.activeElement===el,value:el.value,start:el.selectionStart,end:el.selectionEnd}}`;
let opened = false;
try {
  await request('open', {url:'https://x.com/home'}); opened = true;
  const initial = await evaluate(`async () => {for(let i=0;i<100;i++){const el=document.querySelector('input[aria-label="查询词条"], input[data-testid="SearchBox_Search_Input"]');if(el&&document.querySelectorAll('article').length>1&&document.documentElement.scrollHeight>innerHeight+300){const r=el.getBoundingClientRect();return {x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2),visibility:document.visibilityState,viewport:[innerWidth,innerHeight,devicePixelRatio]}}await new Promise(r=>setTimeout(r,200))}throw Error('Feed/search did not load')}`);
  assert.equal(initial.visibility, 'hidden', 'Keep the acceptance tab in the background');
  const {x,y} = initial;
  for(let sample=0; sample<samples; sample++) {
    async function check(name, setup, commands, verify) {
      await evaluate(setup);
      const measured = [];
      for(const [action,args] of commands) measured.push((await request(action,args,true)).record);
      const passed = await evaluate(verify);
      rows.push({name,sample,passed:passed===true,commands:measured,
        ms:measured.reduce((sum,r)=>sum+r.ms,0),
        request_bytes:measured.reduce((sum,r)=>sum+r.request_bytes,0),
        response_bytes:measured.reduce((sum,r)=>sum+r.response_bytes,0)});
      console.log(JSON.stringify({name,sample,passed}));
    }
    await check('mouse-focus',setupSearch,[['mouse-click',{x,y,button:'left',count:1}]],
      `() => {const el=document.querySelector('input[aria-label="查询词条"], input[data-testid="SearchBox_Search_Input"]');return document.activeElement===el}`);
    const focus = `() => {const el=document.querySelector('input[aria-label="查询词条"], input[data-testid="SearchBox_Search_Input"]');el.value='browser cli';el.focus();el.setSelectionRange(0,0);return true}`;
    await check('tab-default',focus,[['press',{key:'Tab'}]],
      `() => document.activeElement!==document.querySelector('input[aria-label="查询词条"], input[data-testid="SearchBox_Search_Input"]')`);
    await check('select-all',focus,[['press',{key:'Meta+A'}]],
      `() => {const el=document.querySelector('input[aria-label="查询词条"], input[data-testid="SearchBox_Search_Input"]');return el.selectionStart===0&&el.selectionEnd===el.value.length}`);
    await check('backspace-default',focus,[['press',{key:'Meta+ArrowRight'}],['press',{key:'Backspace'}]],
      `() => document.querySelector('input[aria-label="查询词条"], input[data-testid="SearchBox_Search_Input"]').value==='browser cl'`);
    await check('held-shift',focus,[['key-down',{key:'Shift'}],['press',{key:'ArrowRight'}],['key-up',{key:'Shift'}]],
      `() => {const el=document.querySelector('input[aria-label="查询词条"], input[data-testid="SearchBox_Search_Input"]');return el.selectionStart===0&&el.selectionEnd===1}`);
    await check('move-down-up-focus',setupSearch,[['mouse-move',{x,y}],['mouse-down',{button:'left'}],['mouse-up',{button:'left'}]],
      `() => document.activeElement===document.querySelector('input[aria-label="查询词条"], input[data-testid="SearchBox_Search_Input"]')`);
    await check('type-trusted',`async()=>{(${setupSearch})();const el=document.querySelector('input[aria-label="查询词条"], input[data-testid="SearchBox_Search_Input"]');el.focus();window.__bcliTrusted=false;el.addEventListener('input',e=>{window.__bcliTrusted=e.isTrusted},{once:true});return true}`,
      [['type',{text:'browser cli',submit:false}]],
      `()=>window.__bcliTrusted===true&&document.querySelector('input[aria-label="查询词条"], input[data-testid="SearchBox_Search_Input"]').value==='browser cli'`);
    await evaluate(setupSearch);
    await check('scroll-after-move',`async()=>{document.activeElement?.blur();scrollTo(0,0);for(let i=0;i<50&&document.documentElement.scrollHeight<innerHeight+300;i++)await new Promise(r=>setTimeout(r,100));return true}`,
      [['mouse-move',{x:900,y:400}],['scroll',{dx:0,dy:200}]],
      `async()=>{await new Promise(r=>setTimeout(r,200));return scrollY>0}`);
  }
  await evaluate(`()=>{delete window.__bcliTrusted;return true}`);
  const sums = entries => ({calls:entries.length,request_bytes:entries.reduce((n,r)=>n+r.request_bytes,0),response_bytes:entries.reduce((n,r)=>n+r.response_bytes,0)});
  const median = numbers => [...numbers].sort((a,b)=>a-b)[Math.floor(numbers.length/2)];
  const summary = [...new Set(rows.map(r=>r.name))].map(name=>{
    const group=rows.filter(r=>r.name===name);
    return {name,passed:group.filter(r=>r.passed).length,total:group.length,median_ms:median(group.map(r=>r.ms)),
      calls:group.reduce((n,r)=>n+r.commands.length,0),request_bytes:group.reduce((n,r)=>n+r.request_bytes,0),response_bytes:group.reduce((n,r)=>n+r.response_bytes,0)};
  });
  const report={samples,environment:initial,passed:rows.filter(r=>r.passed).length,total:rows.length,
    input_commands:sums(traffic.filter(r=>r.measured)),all_requests:sums(traffic),summary,rows,
    measurement:'Actual newline-terminated daemon request/response UTF-8 bytes. Setup and observation requests are reported separately; no model or real Agent tool calls/tokens are measured. No retries.'};
  mkdirSync(dirname(output),{recursive:true}); writeFileSync(output,JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({report:output,passed:report.passed,total:report.total,input_commands:report.input_commands}));
} finally {if(opened)await request('close');}
