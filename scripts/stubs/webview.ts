/** MOCK_MODE shims for screenshot/tutorial automation. */
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
    setTitle: async (_title: string) => {},
  };
}
