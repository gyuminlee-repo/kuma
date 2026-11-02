//! Replace a file so a reader sees either the old bytes or the new ones.
//!
//! `fs::write` and `File::create` truncate the destination first. If the write
//! then fails (disk full, an unreadable input, a crash) the old file is gone and
//! what is left is partial. Every host file that is replaced in place goes
//! through here instead: the new content is written to a sibling temporary file,
//! flushed to disk, and renamed over the destination. Staying in the same
//! directory keeps the rename on one filesystem, which is what makes it atomic.
//! `std::fs::rename` replaces an existing file on Windows as well as on Unix.

use std::fs::{self, File, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

/// Marker inside every temporary name, so crash debris can be recognised.
const TEMP_MARKER: &str = ".kuma-tmp-";

static COUNTER: AtomicU64 = AtomicU64::new(0);

/// True for a file name this module would use as a temporary file.
pub fn is_temp_name(name: &str) -> bool {
    name.contains(TEMP_MARKER)
}

fn temp_path(dst: &Path) -> io::Result<PathBuf> {
    let name = dst
        .file_name()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "destination has no file name"))?
        .to_string_lossy();
    // The pid keeps two processes off each other's temp file, the counter two
    // threads of this one.
    let unique = format!(
        ".{name}{TEMP_MARKER}{}-{}",
        std::process::id(),
        COUNTER.fetch_add(1, Ordering::Relaxed)
    );
    Ok(dst.with_file_name(unique))
}

/// Removes the temporary file unless the rename has happened.
struct TempGuard {
    path: PathBuf,
    armed: bool,
}

impl Drop for TempGuard {
    fn drop(&mut self) {
        if self.armed {
            let _ = fs::remove_file(&self.path);
        }
    }
}

/// Fill a sibling temporary file with `fill`, then rename it over `dst`.
///
/// `dst` is untouched unless `fill` and the flush both succeed.
pub fn write_atomic_with<T, F>(dst: &Path, fill: F) -> io::Result<T>
where
    F: FnOnce(&mut File) -> io::Result<T>,
{
    let tmp = temp_path(dst)?;
    let mut guard = TempGuard {
        path: tmp.clone(),
        armed: true,
    };
    // No live process shares this name, so a file already there is debris of a
    // crashed process that had the same pid. Clobber it rather than fail the save.
    let mut file = OpenOptions::new()
        .write(true)
        .create(true)
        .truncate(true)
        .open(&tmp)?;
    let value = fill(&mut file)?;
    file.flush()?;
    file.sync_all()?;
    drop(file);
    fs::rename(&tmp, dst)?;
    guard.armed = false;
    Ok(value)
}

/// Write `bytes` to `dst` atomically.
pub fn write_atomic(dst: &Path, bytes: &[u8]) -> io::Result<()> {
    write_atomic_with(dst, |file| file.write_all(bytes))
}
