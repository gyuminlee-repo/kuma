#![cfg(not(target_os = "windows"))]

use kuma_lib::sidecar::LineProtocol;
use serde_json::json;

#[tokio::test]
async fn line_protocol_routes_result_by_id() {
    let protocol = LineProtocol::new();
    let rx = protocol.insert_pending(1).await;

    protocol
        .drain_stdout_chunk(r#"{"jsonrpc":"2.0","id":1,"result":"pong"}"#, |_| {})
        .await;
    protocol.flush_stdout(|_| {}).await;

    let value = rx.await.unwrap().unwrap();
    assert_eq!(value, json!("pong"));
}

#[tokio::test]
async fn line_protocol_marks_ready_from_notification() {
    let protocol = LineProtocol::new();

    protocol
        .drain_stdout_chunk(r#"{"jsonrpc":"2.0","method":"ready","params":{}}"#, |_| {})
        .await;
    protocol.flush_stdout(|_| {}).await;

    protocol
        .wait_ready(std::time::Duration::from_millis(50))
        .await
        .unwrap();
}

// Native lifecycle coverage lives in the harness=false native_sidecar target:
// macOS requires Wry's event loop to run on the executable's main thread.

// rpc_with_timeout 동작 검증:
// SidecarManager 인스턴스화는 AppHandle 필요 → tauri 런타임 없이 불가.
// 대신 timeout이 의존하는 primitive(`tokio::time::timeout` + `oneshot::Receiver`)가
// 응답 없을 때 정확히 지정된 시간 후 만료되는지 직접 검증.
#[tokio::test]
async fn pending_rpc_times_out_after_override_duration() {
    let protocol = LineProtocol::new();
    let rx = protocol.insert_pending(42).await;

    let start = std::time::Instant::now();
    let result = tokio::time::timeout(std::time::Duration::from_millis(50), rx).await;
    let elapsed = start.elapsed();

    assert!(result.is_err(), "expected timeout, got {:?}", result);
    assert!(
        elapsed >= std::time::Duration::from_millis(45),
        "fired too early: {elapsed:?}"
    );
    assert!(
        elapsed < std::time::Duration::from_millis(500),
        "fired too late: {elapsed:?}"
    );
}

#[tokio::test]
async fn pending_rpc_resolves_before_timeout() {
    let protocol = LineProtocol::new();
    let rx = protocol.insert_pending(7).await;

    // 짧은 timeout보다 빠르게 응답 주입.
    protocol
        .drain_stdout_chunk(r#"{"jsonrpc":"2.0","id":7,"result":"ok"}"#, |_| {})
        .await;
    protocol.flush_stdout(|_| {}).await;

    let result = tokio::time::timeout(std::time::Duration::from_millis(500), rx).await;
    let value = result.expect("should not time out").unwrap().unwrap();
    assert_eq!(value, json!("ok"));
}

// ---- A3: stdin writer is separate from termination and inside the deadline ----

mod stdin_writer {
    use kuma_lib::sidecar::{request_with_deadline, LineProtocol, StdinSink, StdinWriter};
    use serde_json::json;
    use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
    use std::sync::{Arc, Condvar, Mutex};
    use std::time::{Duration, Instant};

    /// A child whose stdin pipe is full: writes block until it is killed.
    #[derive(Default)]
    struct Pipe {
        released: Mutex<bool>,
        cv: Condvar,
        block: bool,
        fail: bool,
        started: AtomicUsize,
        force_kills: AtomicUsize,
        handle_killed: AtomicBool,
    }

    impl Pipe {
        fn new(block: bool, fail: bool) -> Arc<Self> {
            Arc::new(Self {
                block,
                fail,
                ..Self::default()
            })
        }

        fn release(&self) {
            *self.released.lock().unwrap() = true;
            self.cv.notify_all();
        }

        fn wait_until(&self, what: &str, done: impl Fn(&Self) -> bool) {
            let start = Instant::now();
            while !done(self) {
                assert!(start.elapsed() < Duration::from_secs(2), "timed out waiting for {what}");
                std::thread::sleep(Duration::from_millis(5));
            }
        }
    }

    struct Sink(Arc<Pipe>);

    impl StdinSink for Sink {
        fn write_line(&mut self, _bytes: &[u8]) -> Result<(), String> {
            self.0.started.fetch_add(1, Ordering::SeqCst);
            if self.0.fail {
                return Err("Broken pipe".into());
            }
            if self.0.block {
                let mut released = self.0.released.lock().unwrap();
                while !*released {
                    released = self.0.cv.wait(released).unwrap();
                }
                return Err("Broken pipe".into());
            }
            Ok(())
        }

        fn kill(self: Box<Self>) -> Result<(), String> {
            self.0.handle_killed.store(true, Ordering::SeqCst);
            Ok(())
        }
    }

    fn writer(pipe: &Arc<Pipe>, protocol: &Arc<LineProtocol>) -> StdinWriter {
        let for_kill = pipe.clone();
        StdinWriter::spawn(
            Sink(pipe.clone()),
            protocol.clone(),
            Box::new(move || {
                for_kill.force_kills.fetch_add(1, Ordering::SeqCst);
                for_kill.release();
            }),
        )
        .unwrap()
    }

    #[tokio::test]
    async fn deadline_covers_a_write_that_never_returns() {
        let pipe = Pipe::new(true, false);
        let protocol = Arc::new(LineProtocol::new());
        let stdin = writer(&pipe, &protocol);
        let started = Instant::now();
        let result = request_with_deadline(
            &stdin,
            &protocol,
            1,
            "ping",
            json!({}),
            Duration::from_millis(200),
        )
        .await;
        assert_eq!(result, Err("RPC timeout: ping after 200ms".to_string()));
        assert!(started.elapsed() < Duration::from_secs(1));
        assert_eq!(pipe.started.load(Ordering::SeqCst), 1);
        stdin.close(true);
    }

    #[tokio::test]
    async fn full_queue_counts_against_the_deadline() {
        let pipe = Pipe::new(true, false);
        let protocol = Arc::new(LineProtocol::new());
        let stdin = writer(&pipe, &protocol);
        // One line stuck in the pipe, then fill the queue behind it.
        stdin.try_send(None, b"stuck\n".to_vec()).unwrap();
        pipe.wait_until("the first write", |p| p.started.load(Ordering::SeqCst) == 1);
        while stdin.try_send(None, b"queued\n".to_vec()).is_ok() {}
        let started = Instant::now();
        let result = request_with_deadline(
            &stdin,
            &protocol,
            2,
            "ping",
            json!({}),
            Duration::from_millis(200),
        )
        .await;
        assert_eq!(result, Err("RPC timeout: ping after 200ms".to_string()));
        assert!(started.elapsed() < Duration::from_secs(1));
        stdin.close(true);
    }

    #[test]
    fn close_during_a_blocked_write_kills_by_pid_without_waiting() {
        let pipe = Pipe::new(true, false);
        let protocol = Arc::new(LineProtocol::new());
        let stdin = writer(&pipe, &protocol);
        stdin.try_send(None, b"stuck\n".to_vec()).unwrap();
        stdin.try_send(None, b"behind\n".to_vec()).unwrap();
        pipe.wait_until("the first write", |p| p.started.load(Ordering::SeqCst) == 1);

        let started = Instant::now();
        stdin.close(true);
        assert!(started.elapsed() < Duration::from_millis(100), "close waited on the writer");
        assert_eq!(pipe.force_kills.load(Ordering::SeqCst), 1);
        pipe.wait_until("the writer to exit", |p| p.handle_killed.load(Ordering::SeqCst));
        assert_eq!(
            pipe.started.load(Ordering::SeqCst),
            1,
            "a line queued behind close was written"
        );
        assert!(stdin.try_send(None, b"late\n".to_vec()).is_err());
    }

    #[test]
    fn close_when_idle_kills_through_the_handle_only() {
        let pipe = Pipe::new(false, false);
        let protocol = Arc::new(LineProtocol::new());
        let stdin = writer(&pipe, &protocol);
        stdin.close(true);
        pipe.wait_until("the writer to exit", |p| p.handle_killed.load(Ordering::SeqCst));
        assert_eq!(pipe.force_kills.load(Ordering::SeqCst), 0);
    }

    #[test]
    fn close_after_exit_never_kills_by_pid() {
        let pipe = Pipe::new(true, false);
        let protocol = Arc::new(LineProtocol::new());
        let stdin = writer(&pipe, &protocol);
        stdin.try_send(None, b"stuck\n".to_vec()).unwrap();
        pipe.wait_until("the first write", |p| p.started.load(Ordering::SeqCst) == 1);
        stdin.close(false);
        assert_eq!(pipe.force_kills.load(Ordering::SeqCst), 0);
        pipe.release();
        pipe.wait_until("the writer to exit", |p| p.handle_killed.load(Ordering::SeqCst));
    }

    /// The exit handler closes without force; a later `kill` closes with
    /// force. The second call must not reach the pid fallback, because the
    /// exited child's pid may already belong to another process.
    #[test]
    fn close_after_exit_ignores_a_later_forced_close() {
        let pipe = Pipe::new(true, false);
        let protocol = Arc::new(LineProtocol::new());
        let stdin = writer(&pipe, &protocol);
        stdin.try_send(None, b"stuck\n".to_vec()).unwrap();
        pipe.wait_until("the first write", |p| p.started.load(Ordering::SeqCst) == 1);
        stdin.close(false);
        stdin.close(true);
        assert_eq!(pipe.force_kills.load(Ordering::SeqCst), 0);
        pipe.release();
        pipe.wait_until("the writer to exit", |p| p.handle_killed.load(Ordering::SeqCst));
    }

    /// B queues behind a stuck write and times out. Once the pipe drains, B
    /// must not be written: its caller was already told it failed.
    #[tokio::test]
    async fn a_request_past_its_deadline_is_never_written() {
        let pipe = Pipe::new(true, false);
        let protocol = Arc::new(LineProtocol::new());
        let stdin = writer(&pipe, &protocol);
        stdin.try_send(None, b"A\n".to_vec()).unwrap();
        pipe.wait_until("the first write", |p| p.started.load(Ordering::SeqCst) == 1);
        let result = request_with_deadline(
            &stdin,
            &protocol,
            4,
            "B",
            json!({}),
            Duration::from_millis(100),
        )
        .await;
        assert_eq!(result, Err("RPC timeout: B after 100ms".to_string()));
        pipe.release();
        // The writer is FIFO: once the sentinel C is written, B has been
        // dequeued, so the count shows whether B was written.
        stdin.try_send(None, b"C\n".to_vec()).unwrap();
        pipe.wait_until("the sentinel", |p| p.started.load(Ordering::SeqCst) >= 2);
        std::thread::sleep(Duration::from_millis(20));
        assert_eq!(pipe.started.load(Ordering::SeqCst), 2, "B was written after its deadline");
        stdin.close(true);
    }

    /// A request that cannot be enqueued leaves no pending entry behind.
    #[tokio::test]
    async fn failed_enqueue_leaves_no_pending_entry() {
        let pipe = Pipe::new(false, false);
        let protocol = Arc::new(LineProtocol::new());
        let stdin = writer(&pipe, &protocol);
        stdin.close(true);
        let result = request_with_deadline(
            &stdin,
            &protocol,
            5,
            "ping",
            json!({}),
            Duration::from_secs(5),
        )
        .await;
        assert_eq!(result, Err("Sidecar not running".to_string()));
        assert_eq!(protocol.pending_len(), 0);
    }

    /// Cancelling the caller while it waits for queue space also cleans up.
    #[tokio::test]
    async fn cancelled_enqueue_leaves_no_pending_entry() {
        let pipe = Pipe::new(true, false);
        let protocol = Arc::new(LineProtocol::new());
        let stdin = writer(&pipe, &protocol);
        stdin.try_send(None, b"stuck\n".to_vec()).unwrap();
        pipe.wait_until("the first write", |p| p.started.load(Ordering::SeqCst) == 1);
        while stdin.try_send(None, b"queued\n".to_vec()).is_ok() {}
        let request = request_with_deadline(
            &stdin,
            &protocol,
            6,
            "ping",
            json!({}),
            Duration::from_secs(30),
        );
        let cancelled = tokio::time::timeout(Duration::from_millis(50), request).await;
        assert!(cancelled.is_err(), "the request should still be waiting for space");
        assert_eq!(protocol.pending_len(), 0);
        stdin.close(true);
    }

    #[tokio::test]
    async fn write_error_fails_the_request_at_once() {
        let pipe = Pipe::new(false, true);
        let protocol = Arc::new(LineProtocol::new());
        let stdin = writer(&pipe, &protocol);
        let started = Instant::now();
        let result = request_with_deadline(
            &stdin,
            &protocol,
            3,
            "ping",
            json!({}),
            Duration::from_secs(5),
        )
        .await;
        assert_eq!(
            result,
            Err("ping: Sidecar stdin write failed: Broken pipe".to_string())
        );
        assert!(started.elapsed() < Duration::from_secs(1));
        stdin.close(true);
    }
}
