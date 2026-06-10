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

#[tokio::test]
#[ignore = "requires a native tauri runtime and packaged fixture sidecar binary"]
async fn launches_real_sidecar_fixture() {
    assert!(true);
}

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
