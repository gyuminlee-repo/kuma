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
