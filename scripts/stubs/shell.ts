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

  stdout = {
    on: (_event: string, _listener: unknown) => {},
  };
  stderr = {
    on: (_event: string, _listener: unknown) => {},
  };

  on(_event: string, _listener: unknown) {
    return this;
  }

  async spawn() {
    return {
      kill: async () => {},
      write: async (_data: string) => {},
      pid: 0,
    };
  }

  async execute() {
    return { code: 0, stdout: "", stderr: "" };
  }
}

export type Child = Awaited<ReturnType<InstanceType<typeof Command>["spawn"]>>;
