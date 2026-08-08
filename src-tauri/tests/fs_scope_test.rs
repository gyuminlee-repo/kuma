//! The fs capability scope, judged by the rule that actually runs on unix.
//!
//! `tauri-plugin-fs` matches its scope patterns with `require_literal_leading_dot`
//! defaulting to `cfg!(unix)` (tauri-plugin-fs 2.5.0, `src/commands.rs`, and the
//! doc comment on `Config` in `src/config.rs`: "Defaults to `true` on Unix systems
//! and `false` on Windows"). Under that rule a pattern whose wildcards have to
//! cross a component beginning with `.` does not match, so `$HOME/**` and even a
//! bare `**` refuse `<project>/.autosave/kuro.json`.
//!
//! The consequence was a platform split that no test could see: every frontend
//! write to a dot path was denied on macOS and Linux and allowed on Windows. The
//! two paths that took are the whole of the app's own persistence, `.autosave/`
//! (both apps' snapshots plus their generations) and `.kuma-workspace.json`, so
//! on macOS a project saved nothing and reopening it restored nothing, silently,
//! while Windows worked. Confirmed on this machine: no project folder written by
//! the macOS build contains either name.
//!
//! These cases pin the fix. They read the shipped capability file rather than a
//! copy of the patterns, and they assert both directions: the dot paths are
//! allowed, and the plain `**` entries still do not reach them on their own, which
//! is what makes the explicit entries load-bearing rather than decorative.
use std::path::Path;

/// Every `path` under the `fs:scope` allow list of the real capability file.
fn allow_patterns() -> Vec<String> {
    let text = std::fs::read_to_string(
        Path::new(env!("CARGO_MANIFEST_DIR")).join("capabilities/default.json"),
    )
    .expect("capabilities/default.json is readable");
    let json: serde_json::Value = serde_json::from_str(&text).expect("capability file is JSON");
    let permissions = json["permissions"]
        .as_array()
        .expect("capability file has permissions");
    let scope = permissions
        .iter()
        .find(|p| p["identifier"] == "fs:scope")
        .expect("capability file declares fs:scope");
    scope["allow"]
        .as_array()
        .expect("fs:scope has an allow list")
        .iter()
        .filter_map(|entry| entry["path"].as_str().map(str::to_string))
        .collect()
}

/// Match one pattern the way the plugin does on unix.
fn matches(pattern: &str, target: &str) -> bool {
    glob::Pattern::new(pattern)
        .unwrap_or_else(|e| panic!("scope pattern {pattern} does not compile: {e}"))
        .matches_path_with(
            Path::new(target),
            glob::MatchOptions {
                // Both flags mirror tauri-plugin-fs. The separator flag is its
                // fix for GHSA-6mv3-wm7j-h4w5; the leading-dot flag is the unix
                // default this test exists for.
                require_literal_separator: true,
                require_literal_leading_dot: true,
                ..Default::default()
            },
        )
}

fn allowed_on_unix(target: &str) -> bool {
    allow_patterns().iter().any(|p| matches(p, target))
}

/// Paths the frontend writes through `@tauri-apps/plugin-fs`, which are the ones
/// this scope has to cover. `.autosave` is `src/lib/autosave.ts`, its generations
/// are `<file>.1`, and the manifest is `src/lib/workspace/types.ts`.
const DOT_PATHS: &[&str] = &[
    "/Users/someone/Documents/kuma/proj/.autosave",
    "/Users/someone/Documents/kuma/proj/.autosave/kuro.json",
    "/Users/someone/Documents/kuma/proj/.autosave/mame.json",
    "/Users/someone/Documents/kuma/proj/.autosave/kuro.json.1",
    "/Users/someone/Documents/kuma/proj/.kuma-workspace.json",
    // A project kept outside the home directory, e.g. an external volume.
    "/Volumes/data/kuma/proj/.autosave/kuro.json",
];

#[test]
fn dot_paths_the_frontend_writes_are_in_scope_on_unix() {
    for target in DOT_PATHS {
        assert!(
            allowed_on_unix(target),
            "{target} is outside the fs scope under the unix matching rule, so the \
             frontend cannot write it on macOS or Linux while Windows can. Add an \
             allow entry naming the dot component literally, such as \
             '**/.autosave/**'.",
        );
    }
}

#[test]
fn plain_wildcards_alone_do_not_reach_dot_paths() {
    // Guards against someone deleting the explicit entries because '**' looks
    // like it already covers everything. It does not, on unix.
    for pattern in ["**", "$HOME/**"] {
        for target in DOT_PATHS {
            assert!(
                !matches(pattern, target),
                "{pattern} unexpectedly matched {target}; if the matching rule \
                 changed, this file's premise needs rechecking",
            );
        }
    }
}

#[test]
fn ordinary_paths_stay_in_scope() {
    for target in [
        "/Users/someone/Documents/kuma/proj/kuma.project.json",
        "/Users/someone/Documents/kuma/proj/design/primers.csv",
    ] {
        assert!(allowed_on_unix(target), "{target} should remain allowed");
    }
}
