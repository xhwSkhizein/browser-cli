import {scrollPageJs} from '../page_runtime.js';
import {keyInput, mouseInput, typeInput, withInputFocus} from '../native_input.js';

export function createInputHandlers(context) {
  return {
    async type(payload) {
      await context.getManagedTab(payload.tab_id);
      return await withInputFocus(payload.tab_id,send=>typeInput(payload.tab_id, payload.text || '', !!payload.submit, send));
    },
    async press(payload) {
      await context.getManagedTab(payload.tab_id);
      return await withInputFocus(payload.tab_id,send=>keyInput(payload.tab_id, 'press', payload.key || '', send));
    },
    async 'key-down'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await withInputFocus(payload.tab_id,send=>keyInput(payload.tab_id, 'key-down', payload.key || '', send));
    },
    async 'key-up'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await withInputFocus(payload.tab_id,send=>keyInput(payload.tab_id, 'key-up', payload.key || '', send));
    },
    async scroll(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.executeExpression(payload.tab_id, scrollPageJs(payload.dx ?? 0, payload.dy ?? 700));
    },
    async 'mouse-move'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await withInputFocus(payload.tab_id,send=>mouseInput(payload.tab_id, 'mouse-move', payload, send));
    },
    async 'mouse-click'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await withInputFocus(payload.tab_id,send=>mouseInput(payload.tab_id, 'mouse-click', payload, send));
    },
    async 'mouse-drag'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await withInputFocus(payload.tab_id,send=>mouseInput(payload.tab_id, 'mouse-drag', payload, send));
    },
    async 'mouse-down'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await withInputFocus(payload.tab_id,send=>mouseInput(payload.tab_id, 'mouse-down', payload, send));
    },
    async 'mouse-up'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await withInputFocus(payload.tab_id,send=>mouseInput(payload.tab_id, 'mouse-up', payload, send));
    },
  };
}
