import {
  keyActionJs,
  mouseActionJs,
  scrollPageJs,
  typeTextJs,
} from '../page_runtime.js';

export function createInputHandlers(context) {
  return {
    async type(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.executeExpression(
        payload.tab_id,
        typeTextJs(payload.text || '', { submit: !!payload.submit }),
      );
    },
    async press(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.executeExpression(payload.tab_id, keyActionJs('press', payload.key || ''));
    },
    async 'key-down'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.executeExpression(payload.tab_id, keyActionJs('key-down', payload.key || ''));
    },
    async 'key-up'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.executeExpression(payload.tab_id, keyActionJs('key-up', payload.key || ''));
    },
    async scroll(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.executeExpression(payload.tab_id, scrollPageJs(payload.dx || 0, payload.dy || 700));
    },
    async 'mouse-move'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.executeExpression(payload.tab_id, mouseActionJs('mouse-move', payload));
    },
    async 'mouse-click'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.executeExpression(payload.tab_id, mouseActionJs('mouse-click', payload));
    },
    async 'mouse-drag'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.executeExpression(payload.tab_id, mouseActionJs('mouse-drag', payload));
    },
    async 'mouse-down'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.executeExpression(payload.tab_id, mouseActionJs('mouse-down', payload));
    },
    async 'mouse-up'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.executeExpression(payload.tab_id, mouseActionJs('mouse-up', payload));
    },
  };
}
