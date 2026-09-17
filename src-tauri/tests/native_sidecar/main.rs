#[cfg(any(target_os = "linux", target_os = "macos"))]
#[path = "mod.rs"]
mod native_sidecar;

#[cfg(any(target_os = "linux", target_os = "macos"))]
use kuma_lib::sidecar_verify;

fn main() {
    #[cfg(any(target_os = "linux", target_os = "macos"))]
    native_sidecar::run();
    #[cfg(not(any(target_os = "linux", target_os = "macos")))]
    eprintln!("native_sidecar: unsupported platform; only Linux and macOS are exercised");
}
