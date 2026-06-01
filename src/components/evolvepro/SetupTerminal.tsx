import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
} from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebglAddon } from "@xterm/addon-webgl";
import "@xterm/xterm/css/xterm.css";
import {
  onPtyOutput,
  ptyKill,
  ptyResize,
  ptySpawn,
  ptyWrite,
} from "@/lib/ipc-evolvepro";

export type SentinelKind = "OK" | "FAIL";
export type SentinelCallback = (
  kind: SentinelKind,
  stepId: string,
  exitCode?: number,
) => void;

export type SetupTerminalHandle = {
  runCommand: (cmd: string) => void;
  runSteps: (
    steps: string[],
    onProgress?: (i: number) => void,
  ) => Promise<void>;
  write: (text: string) => void;
  onSentinel: (prefix: string, cb: SentinelCallback) => () => void;
  /** Send a raw byte sequence (e.g. Ctrl-C "\x03") to the underlying PTY. */
  interrupt: () => void;
};

export type SetupTerminalProps = {
  autoConfirm?: boolean;
  className?: string;
};

const AUTO_CONFIRM_PROMPTS = [
  { pattern: /Proceed \(\[y\]\/n\)\?/, response: "y\r" },
  { pattern: /\(yes\/no\)\??/, response: "yes\r" },
] as const;

function getAutoConfirmResponse(text: string): string | null {
  return AUTO_CONFIRM_PROMPTS.find(({ pattern }) => pattern.test(text))
    ?.response ?? null;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export const SetupTerminal = forwardRef<SetupTerminalHandle, SetupTerminalProps>(
  function SetupTerminal({ autoConfirm = true, className }, ref) {
    const containerRef = useRef<HTMLDivElement | null>(null);
    const termRef = useRef<Terminal | null>(null);
    const fitRef = useRef<FitAddon | null>(null);
    const webglRef = useRef<WebglAddon | null>(null);
    const sessionIdRef = useRef<number | null>(null);
    const bufferRef = useRef<string>("");
    const autoConfirmRef = useRef<boolean>(autoConfirm);
    const sentinelLineBufRef = useRef<string>("");
    const sentinelListenersRef = useRef<
      Array<{ prefix: string; cb: SentinelCallback }>
    >([]);
    // Ring buffer of detected sentinel events. Lets listeners that register
    // after a sentinel arrived still receive it (replay on subscribe).
    const sentinelRingBufRef = useRef<
      Array<{ kind: SentinelKind; stepId: string; exitCode?: number }>
    >([]);

    useEffect(() => {
      autoConfirmRef.current = autoConfirm;
    }, [autoConfirm]);

    useImperativeHandle(
      ref,
      () => ({
        runCommand: (cmd: string) => {
          const sid = sessionIdRef.current;
          if (sid == null) {
            console.warn(
              "[SetupTerminal] runCommand called but PTY session not ready:",
              cmd.substring(0, 80),
            );
            return;
          }
          void ptyWrite(sid, cmd + "\r");
        },
        runSteps: async (
          steps: string[],
          onProgress?: (i: number) => void,
        ) => {
          const sid = sessionIdRef.current;
          if (sid == null) return;
          for (let i = 0; i < steps.length; i++) {
            await ptyWrite(sid, steps[i] + "\r");
            onProgress?.(i);
            await sleep(800);
          }
        },
        write: (text: string) => {
          const term = termRef.current;
          if (!term) return;
          // Normalize LF to CRLF so xterm renders progress lines correctly.
          term.write(text.replace(/\r?\n/g, "\r\n"));
        },
        onSentinel: (prefix: string, cb: SentinelCallback) => {
          const entry = { prefix, cb };
          sentinelListenersRef.current.push(entry);
          console.debug(
            "[SetupTerminal] sentinel listener added; prefix=",
            prefix,
            "total=",
            sentinelListenersRef.current.length,
            "replaying ring buffer entries=",
            sentinelRingBufRef.current.length,
          );
          // Replay buffered sentinels that arrived before this listener was
          // registered. Without this, fast PTY echo can deliver __EP_*_OK__
          // lines before the wizard mounts its callback, breaking the chain.
          for (const event of sentinelRingBufRef.current) {
            const tag = `__EP_${event.stepId}_${event.kind === "OK" ? "OK" : "FAIL"}__`;
            if (!tag.startsWith(prefix)) continue;
            cb(event.kind, event.stepId, event.exitCode);
          }
          return () => {
            sentinelListenersRef.current = sentinelListenersRef.current.filter(
              (e) => e !== entry,
            );
            console.debug(
              "[SetupTerminal] sentinel listener removed; total=",
              sentinelListenersRef.current.length,
            );
          };
        },
        interrupt: () => {
          const sid = sessionIdRef.current;
          if (sid == null) return;
          // SIGINT to the foreground process group in the PTY.
          void ptyWrite(sid, "\x03");
        },
      }),
      [],
    );

    useEffect(() => {
      const container = containerRef.current;
      if (!container) return;

      let cancelled = false;
      let unlistenFn: (() => void) | null = null;
      let resizeObserver: ResizeObserver | null = null;

      const term = new Terminal({
        cursorBlink: true,
        fontSize: 13,
        fontFamily: "monospace",
        theme: { background: "#0b0f17" },
      });
      const fit = new FitAddon();
      term.loadAddon(fit);
      term.open(container);
      try {
        const webgl = new WebglAddon();
        webgl.onContextLoss(() => {
          console.warn(
            "[SetupTerminal] WebGL context lost, falling back to DOM renderer",
          );
          webgl.dispose();
          webglRef.current = null;
        });
        term.loadAddon(webgl);
        webglRef.current = webgl;
      } catch (e) {
        console.warn(
          "[SetupTerminal] WebGL renderer unavailable, falling back to DOM renderer:",
          e,
        );
      }
      fit.fit();
      termRef.current = term;
      fitRef.current = fit;

      void (async () => {
        try {
          const sid = await ptySpawn({ cols: term.cols, rows: term.rows });
          if (cancelled) {
            await ptyKill(sid).catch(() => {});
            return;
          }
          sessionIdRef.current = sid;

          unlistenFn = await onPtyOutput((p) => {
            if (p.session_id !== sessionIdRef.current) return;
            term.write(p.data);
            bufferRef.current = (bufferRef.current + p.data).slice(-256);
            const autoConfirmResponse = autoConfirmRef.current
              ? getAutoConfirmResponse(bufferRef.current)
              : null;
            if (autoConfirmResponse) {
              void ptyWrite(sid, autoConfirmResponse);
              bufferRef.current = "";
            }

            // Sentinel line extraction is listener-independent: parse every
            // chunk into lines, detect __EP_* markers, push to a ring buffer,
            // then dispatch to any currently-registered listeners. A late
            // subscriber replays the ring buffer on registration (see
            // onSentinel handle above), so a sentinel that arrives during
            // the mount race is no longer lost.
            if (p.data.includes("__EP_")) {
              console.debug(
                "[SetupTerminal] raw chunk containing sentinel:",
                JSON.stringify(p.data),
              );
            }
            const combined = sentinelLineBufRef.current + p.data;
            // Split on \n or bare \r so that a sentinel followed by a prompt
            // re-render carriage return (no LF) still terminates the sentinel
            // line for parsing.
            const parts = combined.split(/\r\n|\r|\n/);
            sentinelLineBufRef.current = parts.pop() ?? "";
            // Non-anchored search after stripping ANSI escapes and CR. PSReadLine
            // and other terminal renderers can wrap Write-Host output with color
            // codes or insert cursor-control sequences that defeat strict ^...$
            // anchors. The sentinel ID format (__EP_<UPPER_SNAKE>_OK__) is unique
            // enough that substring search inside a single line is safe.
            const ansiRe = /\x1b\[[0-9;?]*[A-Za-z]/g;
            const okGenRe = /__EP_([A-Z0-9_]+)_OK__/;
            const failGenRe = /__EP_([A-Z0-9_]+)_FAIL__:(\d+)/;
            for (const rawLine of parts) {
              const line = rawLine.replace(/\r/g, "").replace(ansiRe, "");
              const okMatch = okGenRe.exec(line);
              const failMatch = okMatch ? null : failGenRe.exec(line);
              if (!okMatch && !failMatch) continue;
              const event = okMatch
                ? { kind: "OK" as SentinelKind, stepId: okMatch[1], exitCode: undefined as number | undefined }
                : { kind: "FAIL" as SentinelKind, stepId: failMatch![1], exitCode: Number(failMatch![2]) };
              sentinelRingBufRef.current.push(event);
              if (sentinelRingBufRef.current.length > 20) {
                sentinelRingBufRef.current.shift();
              }
              console.debug(
                "[SetupTerminal] sentinel detected:",
                event,
                "listeners=",
                sentinelListenersRef.current.length,
              );
              const tag = `__EP_${event.stepId}_${event.kind === "OK" ? "OK" : "FAIL"}__`;
              for (const { prefix, cb } of sentinelListenersRef.current) {
                if (!tag.startsWith(prefix)) continue;
                cb(event.kind, event.stepId, event.exitCode);
              }
            }
            // Cap pending tail to avoid unbounded growth on no-newline output.
            if (sentinelLineBufRef.current.length > 4096) {
              sentinelLineBufRef.current = sentinelLineBufRef.current.slice(
                -1024,
              );
            }
          });

          term.onData((d) => {
            void ptyWrite(sid, d);
          });
          term.onResize((sz) => {
            void ptyResize(sid, sz.cols, sz.rows);
          });

          resizeObserver = new ResizeObserver(() => {
            try {
              fit.fit();
            } catch {
              // ignore fit errors during teardown
            }
          });
          resizeObserver.observe(container);
        } catch (err) {
          term.write(
            `\r\n\x1b[31m[pty spawn failed]\x1b[0m ${String(err)}\r\n`,
          );
        }
      })();

      return () => {
        cancelled = true;
        if (resizeObserver) {
          resizeObserver.disconnect();
          resizeObserver = null;
        }
        if (unlistenFn) {
          unlistenFn();
          unlistenFn = null;
        }
        const sid = sessionIdRef.current;
        sessionIdRef.current = null;
        if (sid != null) {
          void ptyKill(sid).catch(() => {});
        }
        webglRef.current?.dispose();
        webglRef.current = null;
        term.dispose();
        termRef.current = null;
        fitRef.current = null;
        sentinelListenersRef.current = [];
        sentinelLineBufRef.current = "";
        sentinelRingBufRef.current = [];
      };
    }, []);

    return <div ref={containerRef} className={className} />;
  },
);
