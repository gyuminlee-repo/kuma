/**
 * MOCK_MODE stub for @tauri-apps/api/webview
 */
export function getCurrentWebview() {
  return {
    onDragDropEvent: async (_handler: unknown) => {
      return () => {}; // unlisten
    },
  };
}

export function getCurrentWindow() {
  return {
    metadata: {},
    onCloseRequested: async (_handler: unknown) => () => {},
  };
}
