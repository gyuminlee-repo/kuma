/** MOCK_MODE shims for screenshot/tutorial automation. */
type CloseRequestedEvent = {
  preventDefault: () => void;
};

let closeRequestedHandler: ((event: CloseRequestedEvent) => unknown) | null = null;
let preventDefaultCount = 0;
let closeCount = 0;
let destroyCount = 0;

async function emitCloseRequested() {
  if (!closeRequestedHandler) return;
  await closeRequestedHandler({
    preventDefault: () => {
      preventDefaultCount += 1;
    },
  });
}

export function __resetWindowMock() {
  closeRequestedHandler = null;
  preventDefaultCount = 0;
  closeCount = 0;
  destroyCount = 0;
}

export function __getWindowMockState() {
  return {
    preventDefaultCount,
    closeCount,
    destroyCount,
    hasCloseRequestedHandler: closeRequestedHandler !== null,
  };
}

export async function __emitCloseRequestedForTest() {
  await emitCloseRequested();
}

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
    onCloseRequested: async (handler: (event: CloseRequestedEvent) => unknown) => {
      closeRequestedHandler = handler;
      return () => {
        if (closeRequestedHandler === handler) closeRequestedHandler = null;
      };
    },
    setTitle: async (_title: string) => {},
    close: async () => {
      closeCount += 1;
      await emitCloseRequested();
    },
    destroy: async () => {
      destroyCount += 1;
      await emitCloseRequested();
    },
  };
}
