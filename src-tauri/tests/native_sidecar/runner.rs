use std::{
    os::unix::process::CommandExt,
    path::Path,
    process::{Child, Command, ExitStatus},
    thread,
    time::{Duration, Instant},
};

pub fn process_exists(pid: u32) -> bool {
    let output = Command::new("/bin/ps")
        .args(["-p", &pid.to_string(), "-o", "pid="])
        .output()
        .expect("query OS process table");
    match output.status.code() {
        Some(0) => {
            let observed = String::from_utf8(output.stdout).unwrap();
            assert_eq!(observed.trim().parse::<u32>().unwrap(), pid);
            true
        }
        Some(1) if output.stdout.is_empty() && output.stderr.is_empty() => false,
        _ => panic!("ps failed: {output:?}"),
    }
}

// A separate group lets the supervisor clean up even if the Wry loop hangs.
struct NativeChild(Child);

impl Drop for NativeChild {
    fn drop(&mut self) {
        let result = Command::new("/bin/kill")
            .args(["-KILL", &format!("-{}", self.0.id())])
            .output();
        if let Err(error) = result {
            eprintln!("native process-group cleanup failed: {error}");
        }
        if let Err(error) = self.0.wait() {
            eprintln!("native runner reap failed: {error}");
        }
    }
}

pub fn run(executable: &Path, root: &Path) -> ExitStatus {
    let mut child = NativeChild(
        Command::new(executable)
            .env("RS03_NATIVE_CHILD", "1")
            .env("HOME", root)
            .env("XDG_CONFIG_HOME", root.join("config"))
            .env("XDG_DATA_HOME", root.join(".local/share"))
            .env("XDG_CACHE_HOME", root.join("cache"))
            .process_group(0)
            .spawn()
            .expect("spawn isolated native runner"),
    );
    let deadline = Instant::now() + Duration::from_secs(25);
    loop {
        if let Some(status) = child.0.try_wait().expect("poll native runner") {
            // Check before Drop's emergency cleanup, so leaks cannot pass.
            if let Ok(pid) = std::fs::read_to_string(root.join("fixture.pid")) {
                assert!(
                    !process_exists(pid.trim().parse().unwrap()),
                    "fixture leaked"
                );
            }
            return status;
        }
        assert!(
            Instant::now() < deadline,
            "native runner exceeded 25 seconds"
        );
        thread::sleep(Duration::from_millis(20));
    }
}
