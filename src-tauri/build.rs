fn main() {
    let target = std::env::var("TARGET").expect("TARGET set by cargo");
    println!("cargo:rustc-env=BUILD_TARGET={target}");
    tauri_build::build()
}
