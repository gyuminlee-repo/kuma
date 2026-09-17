# Native host lifecycle smoke

From `src-tauri/`, with the normal Cargo build inputs available:

```sh
# Linux (requires installed GTK/WebKit and Xvfb)
xvfb-run -a cargo test --locked --no-default-features --test native_sidecar
# macOS (requires a desktop session)
cargo test --locked --no-default-features --test native_sidecar
# Existing protocol tests
cargo test --locked --no-default-features --test sidecar_test
```

The `harness = false` target starts a fresh executable whose main thread owns
the real Wry event loop. It includes the production SidecarManager and uses the
real shell plugin and child pipes. The Python executable is only a JSON-RPC
sidecar fixture; there is no simulated app GUI or frozen-sidecar claim.

Assertions cover ready, exact pong, invalid-method survival without respawn,
graceful shutdown receipt, cleared host state, and OS process disappearance.
`ps` first proves the fixture PID exists, then proves it is absent after
shutdown and runner exit. Linux retains its hidden-parent APPDATA regression;
macOS checks its native APPDATA resolver and allowed paths.

Each run uses a temporary HOME and a separate process group. The supervisor
fails after 25 seconds and kills/reaps its child, including the process group
on failure. Leak assertions run before emergency cleanup. Existing negative
controls are `RS03_MUTATION=no-ready`, `wrong-pong`, `die-on-invalid`, and
`ignore-shutdown`; each must fail.

The registered `build.yml` runs this target on `macos-latest`, after its build
inputs are ready. Dispatch that workflow on the pushed code branch. A Linux
pass does not establish macOS success: the macOS runtime step must pass before
merge. Windows is outside this target's coverage.
