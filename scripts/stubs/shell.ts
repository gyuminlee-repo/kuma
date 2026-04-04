/**
 * MOCK_MODE stub for @tauri-apps/plugin-shell
 * No-op implementation used by Playwright capture script.
 */

export class Command {
  static sidecar(_program: string) {
    return new Command();
  }

  static create(_program: string, _args?: string | string[]) {
    return new Command();
  }

  private _stdoutListeners: Array<(data: string) => void> = [];

  stdout = {
    on: (_event: string, listener: (data: string) => void) => {
      if (_event === "data") this._stdoutListeners.push(listener);
    },
  };
  stderr = {
    on: (_event: string, _listener: unknown) => {},
  };

  on(_event: string, _listener: unknown) {
    return this;
  }

  private _emit(line: string) {
    for (const fn of this._stdoutListeners) fn(line);
  }

  async spawn() {
    const self = this;
    // Emit "ready" notification so useSidecar resolves
    setTimeout(() => self._emit('{"jsonrpc":"2.0","method":"ready","params":{}}'), 50);

    return {
      kill: async () => {},
      write: async (data: string) => {
        // Parse JSON-RPC request and return mock response
        try {
          const req = JSON.parse(data);
          const id = req.id;
          let result: unknown = null;

          if (req.method === "list_polymerases") {
            result = [
              { name: "Taq", tm_offset: 0, description: "Standard Taq" },
              { name: "KOD", tm_offset: 3, description: "KOD polymerase" },
              { name: "Phusion", tm_offset: 5, description: "High-fidelity" },
            ];
          } else if (req.method === "analyze_sequence") {
            result = { seq_length: 5000, genes: [], header: "mock" };
          } else {
            result = {};
          }

          setTimeout(() => self._emit(JSON.stringify({ jsonrpc: "2.0", id, result })), 20);
        } catch { /* ignore parse errors */ }
      },
      pid: 0,
    };
  }

  async execute() {
    return { code: 0, stdout: "", stderr: "" };
  }
}

export type Child = Awaited<ReturnType<InstanceType<typeof Command>["spawn"]>>;
