#[test]
fn quit_can_request_close_before_graceful_shutdown_destroys_window() {
    let capability: serde_json::Value =
        serde_json::from_str(include_str!("../capabilities/default.json"))
            .expect("default capability is valid JSON");
    let permissions = capability["permissions"]
        .as_array()
        .expect("default capability declares permissions");
    for permission in ["core:window:allow-close", "core:window:allow-destroy"] {
        assert!(
            permissions.iter().any(|entry| entry == permission),
            "Quit and graceful shutdown require {permission}"
        );
    }
}
