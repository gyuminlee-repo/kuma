use std::{fs, os::unix::fs::PermissionsExt, time::Duration};

mod runner;

// Include the unchanged implementation to observe its private ready/child state.
// AppHandle, Wry, shell spawning, pipe routing and shutdown are all production code.
#[allow(dead_code)]
mod host {
    include!("../../src/sidecar.rs");

    pub async fn exercise(manager: Arc<SidecarManager>) {
        // Given a real Wry host and an executable JSON-RPC fixture.
        assert!(!manager.is_running("kuro").await.unwrap());
        let process = manager.ensure_spawned("kuro").await.expect("native launch");
        let pid = process.pid;
        let root = std::env::current_exe()
            .unwrap()
            .parent()
            .unwrap()
            .to_owned();

        // When requests traverse the native shell plugin and actual child pipes.
        process
            .protocol
            .wait_ready(Duration::from_secs(3))
            .await
            .expect("ready notification");
        assert!(process.protocol.is_ready());
        assert_eq!(
            fs_pid(&root),
            pid,
            "plugin PID must identify the fixture process"
        );
        assert!(super::runner::process_exists(pid), "fixture must be alive");
        assert!(manager.is_running("kuro").await.unwrap());
        let ping = manager
            .rpc_with_timeout("kuro", "ping", json!({}), Some(Duration::from_secs(3)))
            .await;
        assert_eq!(ping, Ok(json!("pong")), "exact ping response");
        let invalid = manager
            .rpc_with_timeout(
                "kuro",
                "rs03.invalid",
                json!({}),
                Some(Duration::from_secs(3)),
            )
            .await;
        assert_eq!(
            invalid,
            Err("rs03.invalid: [-32601] Method not found".into()),
            "invalid request response"
        );
        assert_eq!(
            manager
                .rpc_with_timeout("kuro", "ping", json!({}), Some(Duration::from_secs(3)))
                .await,
            Ok(json!("pong")),
            "ping after invalid request"
        );
        let current = manager.current_process("kuro").await.unwrap().unwrap();
        assert!(
            Arc::ptr_eq(&process, &current),
            "invalid request must not respawn the child"
        );
        assert_eq!(current.pid, pid);

        // Then shutdown reaches the fixture and the OS process and host slot disappear.
        manager.graceful_kill("kuro", 2).await.unwrap();
        let shutdown: Value = serde_json::from_slice(
            &std::fs::read(root.join("shutdown.json")).expect("graceful shutdown receipt"),
        )
        .unwrap();
        assert_eq!(shutdown["method"], "shutdown");
        assert_eq!(shutdown["jsonrpc"], "2.0");
        assert_eq!(shutdown["params"], json!({}));
        assert!(shutdown["id"].is_i64());
        assert!(process.is_terminated());
        assert!(!process.protocol.is_ready());
        assert!(!manager.is_running("kuro").await.unwrap());
        assert!(manager.kuro.lock().await.is_none());
        assert!(manager.current_process("kuro").await.unwrap().is_none());
        assert!(
            !super::runner::process_exists(pid),
            "child still exists after shutdown"
        );
        // A3: a sidecar that stops reading stdin must not stall the host.
        // A request larger than the pipe buffer blocks in the write; the
        // deadline still applies and kill still reaches the child.
        let stalled = manager.ensure_spawned("kuro").await.expect("second launch");
        let stalled_pid = stalled.pid;
        stalled
            .protocol
            .wait_ready(Duration::from_secs(3))
            .await
            .expect("second ready");
        let started = std::time::Instant::now();
        let stall = manager
            .rpc_with_timeout("kuro", "stall", json!({}), Some(Duration::from_millis(500)))
            .await;
        assert!(stall.is_err(), "stall must time out: {stall:?}");
        let big = "x".repeat(4 * 1024 * 1024);
        let blocked = manager
            .rpc_with_timeout(
                "kuro",
                "ping",
                json!({ "pad": big }),
                Some(Duration::from_secs(1)),
            )
            .await;
        assert!(
            matches!(&blocked, Err(err) if err.contains("RPC timeout")),
            "blocked write must end at the deadline: {blocked:?}"
        );
        assert!(
            started.elapsed() < Duration::from_secs(4),
            "deadline overran: {:?}",
            started.elapsed()
        );
        tokio::time::timeout(Duration::from_secs(2), manager.kill("kuro"))
            .await
            .expect("kill must not wait on a blocked stdin write")
            .expect("kill");
        let gone = std::time::Instant::now();
        while super::runner::process_exists(stalled_pid) {
            assert!(
                gone.elapsed() < Duration::from_secs(3),
                "stalled child survived kill"
            );
            tokio::time::sleep(Duration::from_millis(50)).await;
        }
        assert!(manager.kuro.lock().await.is_none());

        // A17: probing health of a stopped sidecar must not start a new one.
        let probe = manager
            .request_existing("kuro", "health_info", json!({}), Duration::from_secs(1))
            .await
            .unwrap();
        assert!(probe.is_none(), "a stopped sidecar must probe as stopped");
        assert!(
            manager.kuro.lock().await.is_none(),
            "health probe respawned a stopped sidecar"
        );

        // A17: a sidecar that exits while its health probe is in flight is
        // stopped, not alive and unresponsive, and is not replaced.
        let dying = manager.ensure_spawned("kuro").await.expect("third launch");
        dying
            .protocol
            .wait_ready(Duration::from_secs(3))
            .await
            .expect("third ready");
        let probe = manager
            .request_existing("kuro", "exit", json!({}), Duration::from_secs(3))
            .await
            .unwrap();
        assert!(probe.is_none(), "an instance that exited mid-probe must probe as stopped");
        assert!(dying.is_terminated());
        assert!(
            manager.current_process("kuro").await.unwrap().is_none(),
            "health probe respawned an exited sidecar"
        );
        manager.kill("kuro").await.unwrap();

        eprintln!(
            "RS03: Wry launch, ready, exact pong, invalid survival, shutdown, stalled-stdin kill, no-spawn health verified; pid={pid}"
        );
    }

    fn fs_pid(root: &std::path::Path) -> u32 {
        std::fs::read_to_string(root.join("fixture.pid"))
            .unwrap()
            .parse()
            .unwrap()
    }
}

pub fn run() {
    if std::env::var_os("RS03_NATIVE_CHILD").is_some() {
        run_native();
        return;
    }
    assert!(
        cfg!(debug_assertions),
        "fixture requires debug build; release integrity checks remain enabled"
    );
    let dir = tempfile::Builder::new()
        .prefix("rs03-native-")
        .tempdir()
        .unwrap();
    // Resolve the temporary directory before the child runs from it. On macOS
    // the system temporary directory sits under /var, which is a symlink to
    // /private/var, and tauri's StartingBinary refuses a current_exe() whose
    // path carries a symlink on that platform: "StartingBinary found
    // current_exe() that contains a symlink on a non-allowed platform: /var".
    // Canonicalizing hands the child the same directory by its real path. The
    // TempDir handle still owns cleanup through its own path.
    let base = dir.path().canonicalize().unwrap();
    let executable = base.join("native-test");
    fs::copy(std::env::current_exe().unwrap(), &executable).unwrap();
    let fixture = base.join("kuro-sidecar");
    fs::write(&fixture, include_bytes!("fixture.py")).unwrap();
    fs::set_permissions(&fixture, fs::Permissions::from_mode(0o700)).unwrap();
    let status = runner::run(&executable, &base);
    if let Ok(pid) = fs::read_to_string(base.join("fixture.pid")) {
        assert!(
            !runner::process_exists(pid.trim().parse().unwrap()),
            "fixture leaked after native runner exit"
        );
    }
    assert!(status.success(), "native runner failed: {status}");
}

fn run_native() {
    let app = tauri::Builder::<tauri::Wry>::default()
        .plugin(tauri_plugin_shell::init())
        .build(tauri::generate_context!(
            "tests/native_sidecar/tauri.conf.json"
        ))
        .expect("real Wry runtime requires a desktop session (Linux: xvfb-run -a)");
    let handle = app.handle().clone();
    verify_app_data_scope(&handle);
    let manager = std::sync::Arc::new(host::SidecarManager::new(
        handle.clone(),
        std::env::temp_dir(),
    ));
    let (send, receive) = std::sync::mpsc::sync_channel(1);
    let mut worker = None;
    app.run_return(move |_, event| {
        if matches!(event, tauri::RunEvent::Ready) {
            let manager = manager.clone();
            let handle = handle.clone();
            let send = send.clone();
            worker = Some(tauri::async_runtime::spawn(async move {
                let task = tauri::async_runtime::spawn(host::exercise(manager.clone()));
                let outcome = task.await;
                manager.kill("kuro").await.expect("cleanup native child");
                send.send(outcome).unwrap();
                handle.exit(0);
            }));
        }
        if matches!(event, tauri::RunEvent::Exit) {
            drop(worker.take());
        }
    });
    receive
        .recv_timeout(Duration::from_secs(2))
        .expect("native worker outcome")
        .expect("native lifecycle assertions");
}

fn verify_app_data_scope(app: &tauri::AppHandle<tauri::Wry>) {
    use tauri::{utils::config::FsScope, Manager};
    let config: serde_json::Value =
        serde_json::from_str(include_str!("../../capabilities/default.json")).unwrap();
    let scope = config["permissions"]
        .as_array()
        .unwrap()
        .iter()
        .find(|entry| entry["identifier"] == "fs:scope")
        .unwrap();
    let paths: Vec<std::path::PathBuf> = scope["allow"]
        .as_array()
        .unwrap()
        .iter()
        .map(|entry| entry["path"].as_str().unwrap().into())
        .collect();
    let without_app_data = paths
        .iter()
        .filter(|path| !path.starts_with("$APPDATA"))
        .cloned()
        .collect();
    let old = tauri::scope::fs::Scope::new(app, &FsScope::AllowedPaths(without_app_data)).unwrap();
    let fixed = tauri::scope::fs::Scope::new(app, &FsScope::AllowedPaths(paths)).unwrap();
    let root = app.path().app_data_dir().unwrap();
    assert_eq!(app.path().parse("$APPDATA").unwrap(), root);
    assert_eq!(app.path().parse("$APPDATA/**").unwrap(), root.join("**"));
    #[cfg(target_os = "linux")]
    assert!(root.components().any(|part| part.as_os_str() == ".local"));
    for path in [root.clone(), root.join("scratch/project.json")] {
        #[cfg(target_os = "linux")]
        assert!(
            !old.is_allowed(&path),
            "old scope must reproduce appData denial: {path:?}"
        );
        assert!(
            fixed.is_allowed(&path),
            "explicit appData scope must allow: {path:?}"
        );
    }
    #[cfg(target_os = "macos")]
    drop(old);
    assert!(!fixed.is_allowed(root.join(".unrelated-secret")));
    eprintln!(
        "CTX01: real Wry APPDATA resolver and hidden-parent scope verified: {}",
        root.display()
    );
}
