import {
  dialogOverrideJs,
  dialogRemoveJs,
} from '../page_runtime.js';
import { handleJavascriptDialog } from '../debugger.js';

export function createDialogHandlers(context) {
  return {
    async 'dialog-setup'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.executeExpression(
        payload.tab_id,
        dialogOverrideJs({ action: payload.action, text: payload.text || null }),
      );
    },
    async dialog(payload) {
      await context.getManagedTab(payload.tab_id);
      await handleJavascriptDialog(payload.tab_id, {
        accept: !payload.dismiss,
        promptText: payload.text || null,
      });
      return { handled: true, accepted: !payload.dismiss, prompt_text: payload.text || null };
    },
    async 'dialog-remove'(payload) {
      await context.getManagedTab(payload.tab_id);
      return await context.executeExpression(payload.tab_id, dialogRemoveJs());
    },
  };
}
