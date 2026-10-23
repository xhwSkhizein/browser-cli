let creatingDocument;

export async function ensureOffscreenDocument() {
  if (!chrome.offscreen) throw new Error('Chrome offscreen documents are not available.');
  if (await chrome.offscreen.hasDocument()) return;
  creatingDocument ||= chrome.offscreen.createDocument({
    url:'offscreen.html',
    reasons:[chrome.offscreen.Reason.DISPLAY_MEDIA, chrome.offscreen.Reason.BLOBS],
    justification:'Encode Browser CLI screenshot and video artifacts.',
  }).finally(() => { creatingDocument = undefined; });
  await creatingDocument;
}

export async function sendOffscreenCommand(command, payload) {
  const response = await chrome.runtime.sendMessage({type:'offscreen-command', command, payload});
  if (!response?.ok) throw new Error(response?.error || `Offscreen command failed: ${command}`);
  return response.data || {};
}
