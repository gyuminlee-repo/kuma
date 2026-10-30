//! Make the operating system show the current app icon after an update.
//!
//! An update replaces the app in place, so the shell keeps serving the icon it
//! cached for that path. Windows is handled twice: the NSIS installer hook
//! (`windows/installer-hooks.nsh`) notifies the shell, and the window gets an
//! explicit `ICON_BIG`, which tauri never sets (it only sets `ICON_SMALL`), so
//! the taskbar stops falling back to the cached exe icon. macOS and AppImage
//! have no installer hook, so the app refreshes once on the first launch of a
//! new version. Every step is best effort: failures are logged and ignored.

use std::fs;
use std::io;
use std::path::{Path, PathBuf};

const MARKER_FILENAME: &str = "last_run_version";

/// True when the version that last ran differs from this one, including the
/// first launch after an update from a build that never wrote the marker.
pub fn should_refresh(previous: Option<&str>, current: &str) -> bool {
    previous.map(str::trim) != Some(current)
}

pub fn marker_path(config_root: &Path) -> PathBuf {
    config_root.join(MARKER_FILENAME)
}

pub fn read_marker(path: &Path) -> Option<String> {
    fs::read_to_string(path).ok()
}

pub fn write_marker(path: &Path, version: &str) -> io::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(path, version)
}

/// `<bundle>.app/Contents/MacOS/<exe>` -> `<bundle>.app`. None outside a bundle
/// (for example `tauri dev`).
pub fn app_bundle_from_exe(exe: &Path) -> Option<PathBuf> {
    let macos = exe.parent()?;
    let contents = macos.parent()?;
    let bundle = contents.parent()?;
    let is_bundle = macos.file_name()? == "MacOS"
        && contents.file_name()? == "Contents"
        && bundle.extension()? == "app";
    is_bundle.then(|| bundle.to_path_buf())
}

/// Icons that libappimage desktop integration (AppImageLauncher and friends)
/// copied for THIS AppImage, paired with the bundled icon of the same size.
///
/// libappimage names them `appimagekit_<id>_<icon>.png` under
/// `<data>/icons/hicolor/<size>/apps/`, where `<id>` is an md5 of the AppImage
/// path. Rather than recompute that hash, the id is read from the integrated
/// desktop file `appimagekit_<id>-<name>.desktop` whose contents name the
/// running AppImage. Only files that already exist are returned, so nothing is
/// created for a user who never integrated the AppImage.
///
/// Assumption: the AppImage path is the first argument of the `Exec=` line,
/// optionally double-quoted (the test fixture uses `Exec=<path> %U`). The path
/// is compared whole, so `kuma.AppImage.old` does not match `kuma.AppImage`.
pub fn appimage_icon_targets(
    applications_dir: &Path,
    icons_dir: &Path,
    appimage: &Path,
    appdir: &Path,
    icon_name: &str,
) -> Vec<(PathBuf, PathBuf)> {
    let Some(appimage) = appimage.to_str() else {
        return Vec::new();
    };
    let Ok(entries) = fs::read_dir(applications_dir) else {
        return Vec::new();
    };
    let ids: Vec<String> = entries
        .flatten()
        .filter_map(|entry| {
            let name = entry.file_name().into_string().ok()?;
            let id = name.strip_prefix("appimagekit_")?.strip_suffix(".desktop")?;
            let (id, _) = id.split_once('-')?;
            let text = fs::read_to_string(entry.path()).ok()?;
            (exec_program(&text)? == appimage).then(|| id.to_string())
        })
        .collect();

    let hicolor = icons_dir.join("hicolor");
    let Ok(sizes) = fs::read_dir(&hicolor) else {
        return Vec::new();
    };
    let sizes: Vec<_> = sizes.flatten().map(|e| e.file_name()).collect();
    let mut targets = Vec::new();
    for id in &ids {
        for size in &sizes {
            let dst = hicolor
                .join(size)
                .join("apps")
                .join(format!("appimagekit_{id}_{icon_name}.png"));
            let src = appdir
                .join("usr/share/icons/hicolor")
                .join(size)
                .join("apps")
                .join(format!("{icon_name}.png"));
            if dst.is_file() && src.is_file() {
                targets.push((src, dst));
            }
        }
    }
    targets
}

/// First argument of the first `Exec=` line, with surrounding double quotes
/// removed and `\"`, `\\` unescaped as the Desktop Entry Spec quotes them.
fn exec_program(desktop: &str) -> Option<String> {
    let value = desktop.lines().find_map(|line| line.strip_prefix("Exec="))?.trim_start();
    if let Some(rest) = value.strip_prefix('"') {
        let mut out = String::new();
        let mut chars = rest.chars();
        while let Some(c) = chars.next() {
            match c {
                '"' => return Some(out),
                '\\' => out.push(chars.next()?),
                _ => out.push(c),
            }
        }
        None
    } else {
        value.split_whitespace().next().map(str::to_string)
    }
}

/// Start the once-per-version refresh on a background thread. No-op on
/// Windows (the installer hook covers it) and on deb installs (dpkg's
/// hicolor-icon-theme trigger rebuilds the cache).
pub fn spawn_refresh_if_updated(config_root: PathBuf, version: String) {
    if !platform_needs_refresh() {
        return;
    }
    std::thread::spawn(move || {
        let marker = marker_path(&config_root);
        if !should_refresh(read_marker(&marker).as_deref(), &version) {
            return;
        }
        let summary = refresh();
        let _ = write_marker(&marker, &version);
        eprintln!("[icon-refresh] {version}: {summary}");
    });
}

fn platform_needs_refresh() -> bool {
    cfg!(target_os = "macos") || (cfg!(target_os = "linux") && std::env::var_os("APPIMAGE").is_some())
}

#[cfg(target_os = "macos")]
fn refresh() -> String {
    use std::process::{Command, Stdio};
    const LSREGISTER: &str = "/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister";
    let Some(bundle) = std::env::current_exe().ok().and_then(|e| app_bundle_from_exe(&e)) else {
        return "not running from an .app bundle, skipped".into();
    };
    let quiet = |cmd: &mut Command| {
        cmd.stdout(Stdio::null()).stderr(Stdio::null()).status().map(|s| s.success()).unwrap_or(false)
    };
    let touched = quiet(Command::new("touch").arg(&bundle));
    let registered = quiet(Command::new(LSREGISTER).arg("-f").arg(&bundle));
    format!("{} touch={touched} lsregister={registered}", bundle.display())
}

#[cfg(target_os = "linux")]
fn refresh() -> String {
    use std::process::{Command, Stdio};
    let (Some(appimage), Some(appdir), Some(data)) = (
        std::env::var_os("APPIMAGE").map(PathBuf::from),
        std::env::var_os("APPDIR").map(PathBuf::from),
        dirs::data_dir(),
    ) else {
        return "APPIMAGE, APPDIR or data dir unknown, skipped".into();
    };
    let icon_name = std::env::current_exe()
        .ok()
        .and_then(|e| e.file_stem().map(|s| s.to_string_lossy().into_owned()))
        .unwrap_or_default();
    if icon_name.is_empty() {
        return "executable name unknown, skipped".into();
    }
    let icons = data.join("icons");
    let targets = appimage_icon_targets(&data.join("applications"), &icons, &appimage, &appdir, &icon_name);
    if targets.is_empty() {
        return "no integrated icons for this AppImage".into();
    }
    let replaced = targets.iter().filter(|(src, dst)| replace_file(src, dst).is_ok()).count();
    // The Icon Theme Spec (Implementation Notes) has caching readers watch the
    // mtime of the toplevel theme directory, not of the size subdirectory the
    // rename touched, so bump it explicitly.
    let hicolor = icons.join("hicolor");
    let _ = Command::new("touch").arg(&hicolor).stdout(Stdio::null()).stderr(Stdio::null()).status();
    // Only rebuild a cache that already exists; creating one would make a
    // directory that nothing else keeps current go stale later.
    let cache = if hicolor.join("icon-theme.cache").is_file() {
        Command::new("gtk-update-icon-cache")
            .args(["-f", "-t", "-q"])
            .arg(&hicolor)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .map(|s| s.success().to_string())
            .unwrap_or_else(|_| "unavailable".into())
    } else {
        "none".into()
    };
    format!("replaced {replaced}/{} integrated icons, cache={cache}", targets.len())
}

#[cfg(not(any(target_os = "macos", target_os = "linux")))]
fn refresh() -> String {
    "nothing to do on this platform".into()
}

/// Copy beside the destination and rename over it, so a reader never sees a
/// half-written icon.
#[cfg(target_os = "linux")]
fn replace_file(src: &Path, dst: &Path) -> io::Result<()> {
    // The pid keeps two processes refreshing the same icon off each other's
    // temp file. Staying in dst's directory keeps the rename atomic.
    let tmp = dst.with_extension(format!("png.kuma-tmp-{}", std::process::id()));
    let cleanup = |_: &io::Error| {
        let _ = fs::remove_file(&tmp);
    };
    fs::copy(src, &tmp).inspect_err(cleanup)?;
    fs::rename(&tmp, dst).inspect_err(cleanup)
}

/// Give the window the exe icon (resource 32512, the one tauri-build embeds)
/// as `ICON_BIG`. Tauri sets only `ICON_SMALL`, and without a big icon the
/// taskbar uses the shell icon cached for the exe path, which an in-place
/// update leaves at the old picture.
#[cfg(windows)]
pub fn set_taskbar_icon(window: &tauri::WebviewWindow) {
    use windows::core::PCWSTR;
    use windows::Win32::Foundation::{HWND, LPARAM, WPARAM};
    use windows::Win32::System::LibraryLoader::GetModuleHandleW;
    use windows::Win32::UI::WindowsAndMessaging::{
        LoadImageW, SendMessageW, ICON_BIG, IMAGE_ICON, LR_DEFAULTSIZE, LR_SHARED, WM_SETICON,
    };
    const APP_ICON_RESOURCE: usize = 32512;
    let Ok(hwnd): Result<HWND, _> = window.hwnd() else {
        eprintln!("[icon-refresh] no HWND for {}, taskbar icon not set", window.label());
        return;
    };
    // Width and height 0 with LR_DEFAULTSIZE load the SM_CXICON x SM_CYICON
    // frame. LR_SHARED leaves the handle to the system, so it is never freed
    // while the window still uses it.
    let handle = unsafe {
        LoadImageW(
            GetModuleHandleW(PCWSTR::null()).map(Into::into).ok(),
            PCWSTR::from_raw(APP_ICON_RESOURCE as *const u16),
            IMAGE_ICON,
            0,
            0,
            LR_DEFAULTSIZE | LR_SHARED,
        )
    };
    match handle {
        Ok(icon) => unsafe {
            SendMessageW(hwnd, WM_SETICON, Some(WPARAM(ICON_BIG as _)), Some(LPARAM(icon.0 as _)));
        },
        Err(e) => eprintln!("[icon-refresh] LoadImageW failed, taskbar icon not set: {e}"),
    }
}
