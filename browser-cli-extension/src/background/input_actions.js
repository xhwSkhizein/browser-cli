import {scrollPageJs} from '../page_runtime.js';
import {keyInput, mouseInput, typeInput} from '../native_input.js';

export function createInputHandlers(context) {
  return {
    async type(payload) {
      await context.getManagedTab(payload.tab_id);
      return await typeInput(payload.tab_id, payload.text || '', !!payload.submit);
    },
    async press(payload) {
      await context.getManagedTab(payload.tab_id);
      return await keyInput(payload.tab_id, 'press', payload.key || '');
    },
    async 'key-down'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await keyInput(payload.tab_id, 'key-down', payload.key || '');
    },
    async 'key-up'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await keyInput(payload.tab_id, 'key-up', payload.key || '');
    },
    async scroll(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.executeExpression(payload.tab_id, scrollPageJs(payload.dx ?? 0, payload.dy ?? 700));
    },
    async 'mouse-move'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await mouseInput(payload.tab_id, 'mouse-move', payload);
    },
    async 'mouse-click'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await mouseInput(payload.tab_id, 'mouse-click', payload);
    },
    async 'mouse-drag'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await mouseInput(payload.tab_id, 'mouse-drag', payload);
    },
    async 'mouse-down'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await mouseInput(payload.tab_id, 'mouse-down', payload);
    },
    async 'mouse-up'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await mouseInput(payload.tab_id, 'mouse-up', payload);
    },
  };
}
