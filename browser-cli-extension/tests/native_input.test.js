import test from 'node:test';
import assert from 'node:assert/strict';
import {createInputHandlers} from '../src/background/input_actions.js';
import {forgetInputState, keyInput, mouseInput, typeInput, withInputFocus} from '../src/native_input.js';
import {registerDebuggerListeners} from '../src/debugger.js';
import {scrollPageJs} from '../src/page_runtime.js';
import {runInNewContext} from 'node:vm';

function setup(t) {
  const calls=[];
  const listeners={};
  let tabGets=0, attaches=0;
  globalThis.chrome={runtime:{async getPlatformInfo(){return {os:'mac'}}},
    tabs:{async get(id){tabGets++;return {id,url:'https://fixture.test/'}},onRemoved:{addListener(fn){listeners.removed=fn}}},
    debugger:{async attach(){attaches++;},async sendCommand(_target,method,params){calls.push({method,params});return {}},
      onDetach:{addListener(fn){listeners.detached=fn}},onEvent:{addListener(){}}}};
  forgetInputState(700);
  t.after(()=>{forgetInputState(700);delete globalThis.chrome});
  return {calls,listeners,counts:()=>({tabGets,attaches})};
}
test('background focus is temporary and cleanup preserves an input failure without replay',async t=>{
  const {calls}=setup(t);
  assert.deepEqual(await withInputFocus(700,()=>mouseInput(700,'mouse-click',{x:20,y:30})),{x:20,y:30,button:'left',count:1});
  assert.deepEqual(calls.filter(c=>c.method==='Emulation.setFocusEmulationEnabled').map(c=>c.params.enabled),[true,false]);
  calls.length=0;
  await assert.rejects(withInputFocus(700,async()=>{throw Error('input failed')}),/input failed/);
  assert.deepEqual(calls.map(c=>c.params.enabled),[true,false]);
  const original=chrome.debugger.sendCommand;
  chrome.debugger.sendCommand=async(target,method,params)=>{
    if(params.enabled===false) throw Error('cleanup failed');
    return original(target,method,params);
  };
  await assert.rejects(withInputFocus(700,async()=>{throw Error('primary input failure')}),/primary input failure/);
});
test('keyboard preserves held modifiers, native editing commands and compact results',async t=>{
  const {calls}=setup(t);
  assert.deepEqual(await keyInput(700,'key-down','Shift'),{key:'Shift'});
  assert.deepEqual(await keyInput(700,'press','ArrowRight'),{key:'ArrowRight'});
  assert.equal(calls[1].params.modifiers,8);
  assert.deepEqual(calls[1].params.commands,['moveRightAndModifySelection']);
  assert.equal(calls[2].params.modifiers,8);
  await keyInput(700,'key-up','Shift');
  assert.equal(calls[3].params.modifiers,0);
  await keyInput(700,'press','ControlOrMeta+A');
  assert.equal(calls[5].params.code,'KeyA');
  assert.deepEqual(calls[5].params.commands,['selectAll']);
  assert.equal(calls[5].params.text,'');
  assert.equal(calls.at(-1).params.modifiers,0);
});
test('literal plus, shifted character, async text insertion and Enter use native input',async t=>{
  const {calls}=setup(t);
  await keyInput(700,'press','Control++');
  assert.equal(calls[1].params.key,'+');
  await keyInput(700,'press','Shift+a');
  assert.equal(calls[5].params.key,'A');
  assert.equal(calls[5].params.text,'A');
  assert.deepEqual(await typeInput(700,'中文😀',true),{typed:true,submitted:true});
  assert.equal(calls[8].method,'Input.insertText');
  assert.deepEqual(calls[8].params,{text:'中文😀'});
  assert.equal(calls[9].params.key,'Enter');
});
test('releasing one side of a modifier retains the other held key',async t=>{
  const {calls}=setup(t);
  await keyInput(700,'key-down','ShiftLeft');
  await keyInput(700,'key-down','ShiftRight');
  await keyInput(700,'key-up','ShiftLeft');
  assert.equal(calls.at(-1).params.modifiers,8);
  await keyInput(700,'key-up','ShiftRight');
  assert.equal(calls.at(-1).params.modifiers,0);
});
test('invalid combinations fail before any input; protocol errors never replay',async t=>{
  const {calls}=setup(t);
  for(const key of ['Control+BadKey','a+b','']) await assert.rejects(keyInput(700,'press',key));
  assert.equal(calls.length,0);
  chrome.debugger.sendCommand=async (_target,method,params)=>{calls.push({method,params});throw Error('protocol failure')};
  await assert.rejects(mouseInput(700,'mouse-click',{x:30,y:40}),/protocol failure/);
  assert.equal(calls.length,1);
});
test('mouse down/up follow the last CSS position, preserve buttons and reset on detach',async t=>{
  const {calls,listeners}=setup(t);
  registerDebuggerListeners(forgetInputState);
  assert.deepEqual(await mouseInput(700,'mouse-move',{x:31,y:42}),{x:31,y:42});
  assert.deepEqual(await mouseInput(700,'mouse-down',{button:'left'}),{button:'left'});
  assert.deepEqual(await mouseInput(700,'mouse-up',{button:'left'}),{button:'left'});
  assert.deepEqual(calls.map(c=>[c.params.x,c.params.y,c.params.buttons]),[[31,42,0],[31,42,1],[31,42,0]]);
  await keyInput(700,'key-down','Shift');
  listeners.detached({tabId:700});
  await mouseInput(700,'mouse-down',{button:'right'});
  assert.equal(calls.at(-1).params.x,0);
  assert.equal(calls.at(-1).params.modifiers,0);
});
test('drag and multi-click preserve result shape and click sequence',async t=>{
  const {calls}=setup(t);
  assert.deepEqual(await mouseInput(700,'mouse-click',{x:40,y:50,count:2}),{x:40,y:50,button:'left',count:2});
  assert.deepEqual(calls.map(c=>c.params.clickCount),[0,1,1,2,2]);
  calls.length=0;
  assert.deepEqual(await mouseInput(700,'mouse-drag',{x1:10,y1:20,x2:30,y2:40}),{from:{x:10,y:20},to:{x:30,y:40}});
  assert.deepEqual(calls.map(c=>c.params.type),['mouseMoved','mousePressed','mouseMoved','mouseReleased']);
  assert.equal(calls[2].params.buttons,1);
});
test('ownership checks precede native input and zero scroll does not become 700 pixels',async t=>{
  const {calls}=setup(t);
  const handlers=createInputHandlers({async getManagedTab(){throw Error('not owned')}});
  await assert.rejects(handlers['mouse-click']({tab_id:700,x:10,y:20}),/not owned/);
  assert.equal(calls.length,0);
  let delta;
  const window={scrollX:0,scrollY:0,scrollBy(x,y){delta=[x,y]}};
  runInNewContext(scrollPageJs(0,0),{window,document:{dispatchEvent(){}},WheelEvent:class{}});
  assert.deepEqual(delta,[0,0]);
});

test('one native command prepares its connection once, retaining focus cleanup and result',async t=>{
  const {calls,counts}=setup(t);
  const handlers=createInputHandlers({async getManagedTab(id){return await chrome.tabs.get(id)}});
  const start=counts().tabGets;
  assert.deepEqual(await handlers['mouse-click']({tab_id:700,x:20,y:30}),{x:20,y:30,button:'left',count:1});
  assert.equal(counts().tabGets-start,2); // Ownership check plus one debugger preparation.
  assert.deepEqual(calls.map(c=>c.method),['Emulation.setFocusEmulationEnabled',
    'Input.dispatchMouseEvent','Input.dispatchMouseEvent','Input.dispatchMouseEvent','Emulation.setFocusEmulationEnabled']);
  const next=counts().tabGets;
  await handlers.press({tab_id:700,key:'Meta+A'});
  assert.equal(counts().tabGets-next,2); // Every command prepares again, including multi-key input.
  const typed=counts().tabGets;
  await handlers.type({tab_id:700,text:'hello',submit:true});
  assert.equal(counts().tabGets-typed,2);
  const dragged=counts().tabGets;
  await handlers['mouse-drag']({tab_id:700,x1:10,y1:20,x2:30,y2:40});
  assert.equal(counts().tabGets-dragged,2);
});
test('lost debugger during input fails without attaching or replaying the remaining events',async t=>{
  const {calls,counts,listeners}=setup(t);
  registerDebuggerListeners(forgetInputState);
  const initialAttaches=counts().attaches;
  const handlers=createInputHandlers({async getManagedTab(id){return await chrome.tabs.get(id)}});
  const original=chrome.debugger.sendCommand;
  chrome.debugger.sendCommand=async(target,method,params)=>{
    if(method==='Input.dispatchMouseEvent'&&params.type==='mousePressed'){
      calls.push({method,params});listeners.detached({tabId:700});throw Error('Debugger detached');
    }
    return original(target,method,params);
  };
  await assert.rejects(handlers['mouse-click']({tab_id:700,x:20,y:30}),/Debugger detached/);
  assert.equal(counts().tabGets,2);
  assert.equal(counts().attaches,initialAttaches);
  assert.equal(calls.filter(c=>c.params.type==='mousePressed').length,1);
  assert.equal(calls.filter(c=>c.params.type==='mouseReleased').length,0);
  assert.equal(calls.at(-1).params.enabled,false);
});
