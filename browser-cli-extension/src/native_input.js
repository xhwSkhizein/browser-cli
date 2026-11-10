import {sendCommand} from './debugger.js';
import {USKeyboardLayout, macEditingCommands} from './key_definitions.js';

const states = new Map();
const modifierBits = {Alt:1, Control:2, Meta:4, Shift:8};
const aliases = {Shift:'ShiftLeft', Control:'ControlLeft', Alt:'AltLeft', Meta:'MetaLeft', '\n':'Enter', '\r':'Enter'};
const keys = new Map();
for (const [code, definition] of Object.entries(USKeyboardLayout)) {
  const base = {...definition, code, text:definition.text || (definition.key.length===1 ? definition.key : '')};
  const shifted = definition.shiftKey ? {...base, key:definition.shiftKey, text:definition.shiftKey,
    keyCode:definition.shiftKeyCode || definition.keyCode} : undefined;
  keys.set(code, {...base, shifted});
  if (!definition.location && definition.key.length===1) keys.set(definition.key, {...base, shifted});
  if (!definition.location && shifted) keys.set(shifted.key, shifted);
}
for (const [alias, code] of Object.entries(aliases)) keys.set(alias, keys.get(code));
let platform;
const isMac = () => platform ||= chrome.runtime.getPlatformInfo().then(info=>info.os==='mac');
const stateFor = tabId => {
  if (!states.has(tabId)) states.set(tabId, {x:0,y:0,buttons:0,keys:new Set(),modifiers:0});
  return states.get(tabId);
};
export function forgetInputState(tabId) { states.delete(tabId); }

async function definition(key) {
  if (key==='ControlOrMeta') key=(await isMac()) ? 'Meta' : 'Control';
  const result=keys.get(key);
  if (!result) throw new Error(`Unknown key: ${key}`);
  return result;
}
async function dispatchKey(tabId, base, up) {
  const state=stateFor(tabId);
  const key=(state.modifiers & 8) && base.shifted ? base.shifted : base;
  const held=new Set(state.keys);
  if (up) held.delete(key.code); else held.add(key.code);
  const modifiers=[...held].reduce((mask,code)=>mask | (modifierBits[keys.get(code)?.key] || 0),0);
  const text=(modifiers & ~8) ? '' : key.text;
  const shortcut=[...['Shift','Control','Alt','Meta'].filter(name=>modifiers & modifierBits[name]),key.code].join('+');
  const commands=(await isMac()) ? [macEditingCommands[shortcut] || []].flat()
    .filter(command=>!command.startsWith('insert')).map(command=>command.slice(0,-1)) : [];
  await sendCommand(tabId,'Input.dispatchKeyEvent',{
    type:up ? 'keyUp' : text ? 'keyDown' : 'rawKeyDown',
    key:key.key, code:key.code, windowsVirtualKeyCode:key.keyCodeWithoutLocation || key.keyCode,
    location:key.location || 0, isKeypad:key.location===3, modifiers,
    ...(up ? {} : {text,unmodifiedText:text,commands,autoRepeat:state.keys.has(key.code)}),
  });
  state.modifiers=modifiers;
  if (up) state.keys.delete(key.code); else state.keys.add(key.code);
}
export async function keyInput(tabId, action, key) {
  if (action!=='press') {
    await dispatchKey(tabId,await definition(key),action==='key-up');
    return {key};
  }
  // A trailing plus is a literal key, as in Control++.
  const tokens=key.split('+');
  if (key.endsWith('+')) {tokens.pop();tokens[tokens.length-1]='+';}
  const definitions=await Promise.all(tokens.map(definition));
  if (!definitions.length || definitions.slice(0,-1).some(item=>!modifierBits[item.key])) throw new Error(`Invalid key combination: ${key}`);
  const state=stateFor(tabId);
  const added=[];
  for (const item of definitions.slice(0,-1)) {
    if (!(state.modifiers & modifierBits[item.key])) {await dispatchKey(tabId,item,false);added.push(item);}
  }
  // Never replay input after a protocol failure; held-state cleanup belongs to the caller.
  await dispatchKey(tabId,definitions.at(-1),false);
  await dispatchKey(tabId,definitions.at(-1),true);
  for (const item of added.reverse()) await dispatchKey(tabId,item,true);
  return {key};
}
export async function typeInput(tabId, text, submit) {
  if (text) await sendCommand(tabId,'Input.insertText',{text});
  if (submit) await keyInput(tabId,'press','Enter');
  return {typed:true,submitted:!!submit};
}
const buttonBits={left:1,right:2,middle:4};
async function mouseEvent(tabId,type,x,y,button='none',clickCount=0) {
  if (!Number.isFinite(x)||!Number.isFinite(y)||x<0||y<0) throw new Error('Mouse coordinates must be nonnegative CSS viewport pixels.');
  const state=stateFor(tabId);
  const bit=buttonBits[button] || 0;
  const buttons=type==='mousePressed' ? state.buttons | bit : type==='mouseReleased' ? state.buttons & ~bit : state.buttons;
  await sendCommand(tabId,'Input.dispatchMouseEvent',{type,x,y,button,buttons,clickCount,modifiers:state.modifiers});
  Object.assign(state,{x,y,buttons});
}
export async function mouseInput(tabId,action,payload) {
  const button=payload.button || 'left';
  if (!buttonBits[button]) throw new Error(`Unknown mouse button: ${button}`);
  const state=stateFor(tabId);
  if (action==='mouse-move') {
    await mouseEvent(tabId,'mouseMoved',payload.x,payload.y);
    return {x:payload.x,y:payload.y};
  }
  if (action==='mouse-down'||action==='mouse-up') {
    await mouseEvent(tabId,action==='mouse-down'?'mousePressed':'mouseReleased',state.x,state.y,button,1);
    return {button};
  }
  if (action==='mouse-drag') {
    if (![payload.x1,payload.y1,payload.x2,payload.y2].every(n=>Number.isFinite(n)&&n>=0)) throw new Error('Invalid CSS drag coordinates.');
    await mouseEvent(tabId,'mouseMoved',payload.x1,payload.y1);
    await mouseEvent(tabId,'mousePressed',payload.x1,payload.y1,button,1);
    await mouseEvent(tabId,'mouseMoved',payload.x2,payload.y2,button,1);
    await mouseEvent(tabId,'mouseReleased',payload.x2,payload.y2,button,1);
    return {from:{x:payload.x1,y:payload.y1},to:{x:payload.x2,y:payload.y2}};
  }
  const count=Math.max(1,Number(payload.count || 1));
  if (!Number.isSafeInteger(count)) throw new Error('Invalid mouse click count.');
  await mouseEvent(tabId,'mouseMoved',payload.x,payload.y);
  for (let i=1;i<=count;i++) {
    await mouseEvent(tabId,'mousePressed',payload.x,payload.y,button,i);
    await mouseEvent(tabId,'mouseReleased',payload.x,payload.y,button,i);
  }
  return {x:payload.x,y:payload.y,button,count};
}
