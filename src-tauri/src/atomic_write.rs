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

/// Every temporary name is this prefix, the pid, `-`, and a counter, and
/// nothing else, so crash debris can be told from project files exactly.
/// The destination name is deliberately left out: a destination whose name is
/// already near the filesystem limit would otherwise get an over-long sibling.
const TEMP_PREFIX: &str = ".kuma-tmp-";

/// Names tried before giving up. Every collision is a file this call did not
/// create (debris, or something planted), and it is never opened.
const MAX_ATTEMPTS: usize = 64;

static COUNTER: AtomicU64 = AtomicU64::new(0);

/// True only for a name this module creates: `.kuma-tmp-<digits>-<digits>`.
pub fn is_temp_name(name: &str) -> bool {
    let Some(rest) = name.strip_prefix(TEMP_PREFIX) else {
        return false;
    };
    let Some((pid, counter)) = rest.split_once('-') else {
        return false;
    };
    let digits = |part: &str| !part.is_empty() && part.bytes().all(|b| b.is_ascii_digit());
    digits(pid) && digits(counter)
}

/// Fresh candidate names in the destination's directory.
fn temp_candidates(dst: &Path) -> io::Result<impl Iterator<Item = PathBuf> + '_> {
    if dst.file_name().is_none() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "destination has no file name",
        ));
    }
    // The pid keeps two processes apart, the counter two calls of this one.
    // A crashed process with a reused pid can still have left a name behind;
    // exclusive creation then fails and the next counter value is tried.
    Ok(std::iter::repeat_with(move || {
        let n = COUNTER.fetch_add(1, Ordering::Relaxed);
        dst.with_file_name(format!("{TEMP_PREFIX}{}-{n}", std::process::id()))
    }))
}

/// Removes the temporary file unless the rename has happened. Only created
/// once this call has made the file itself, so it never removes a file that
/// something else put at a colliding name.
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

/// Create a new file at the first free candidate. `create_new` fails on any
/// existing entry, a symlink included, so nothing already there is followed
/// or truncated.
fn create_temp(candidates: impl Iterator<Item = PathBuf>) -> io::Result<(File, TempGuard)> {
    let mut last = None;
    for path in candidates.take(MAX_ATTEMPTS) {
        match OpenOptions::new().write(true).create_new(true).open(&path) {
            Ok(file) => return Ok((file, TempGuard { path, armed: true })),
            Err(err) if err.kind() == io::ErrorKind::AlreadyExists => last = Some(err),
            Err(err) => return Err(err),
        }
    }
    Err(last.unwrap_or_else(|| {
        io::Error::new(io::ErrorKind::AlreadyExists, "no free temporary file name")
    }))
}

/// Fill a sibling temporary file with `fill`, then rename it over `dst`.
///
/// `dst` is untouched unless `fill` and the flush both succeed.
pub fn write_atomic_with<T, F>(dst: &Path, fill: F) -> io::Result<T>
where
    F: FnOnce(&mut File) -> io::Result<T>,
{
    write_atomic_in(dst, temp_candidates(dst)?, fill)
}

fn write_atomic_in<T, F>(
    dst: &Path,
    candidates: impl Iterator<Item = PathBuf>,
    fill: F,
) -> io::Result<T>
where
    F: FnOnce(&mut File) -> io::Result<T>,
{
    let (mut file, mut guard) = create_temp(candidates)?;
    let value = fill(&mut file)?;
    file.flush()?;
    file.sync_all()?;
    drop(file);
    fs::rename(&guard.path, dst)?;
    guard.armed = false;
    Ok(value)
}

/// Write `bytes` to `dst` atomically.
pub fn write_atomic(dst: &Path, bytes: &[u8]) -> io::Result<()> {
    write_atomic_with(dst, |file| file.write_all(bytes))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[cfg(unix)]
    #[test]
    fn a_symlink_at_the_temporary_name_is_neither_followed_nor_removed() {
        let dir = tempfile::tempdir().unwrap();
        let outside = dir.path().join("outside.txt");
        fs::write(&outside, "keep me").unwrap();
        let planted = dir.path().join(".kuma-tmp-1-0");
        std::os::unix::fs::symlink(&outside, &planted).unwrap();
        let free = dir.path().join(".kuma-tmp-1-1");
        let dst = dir.path().join("config.json");

        write_atomic_in(&dst, [planted.clone(), free].into_iter(), |f| {
            f.write_all(b"new")
        })
        .unwrap();

        assert_eq!(fs::read_to_string(&outside).unwrap(), "keep me");
        assert_eq!(fs::read_to_string(&dst).unwrap(), "new");
        assert!(fs::symlink_metadata(&planted).unwrap().file_type().is_symlink());
    }

    #[test]
    fn a_debris_file_at_the_temporary_name_is_left_alone() {
        let dir = tempfile::tempdir().unwrap();
        let debris = dir.path().join(".kuma-tmp-1-0");
        fs::write(&debris, "old").unwrap();
        let dst = dir.path().join("a.json");
        write_atomic_in(
            &dst,
            [debris.clone(), dir.path().join(".kuma-tmp-1-1")].into_iter(),
            |f| f.write_all(b"new"),
        )
        .unwrap();
        assert_eq!(fs::read_to_string(&debris).unwrap(), "old");
        assert_eq!(fs::read_to_string(&dst).unwrap(), "new");
    }

    #[test]
    fn a_failed_fill_removes_only_its_own_temporary_file() {
        let dir = tempfile::tempdir().unwrap();
        let dst = dir.path().join("a.json");
        fs::write(&dst, "old").unwrap();
        let err = write_atomic_with(&dst, |_| -> io::Result<()> {
            Err(io::Error::other("boom"))
        })
        .unwrap_err();
        assert_eq!(err.to_string(), "boom");
        assert_eq!(fs::read_to_string(&dst).unwrap(), "old");
        let names: Vec<_> = fs::read_dir(dir.path()).unwrap().collect();
        assert_eq!(names.len(), 1);
    }

    #[test]
    fn a_destination_name_near_the_limit_still_saves() {
        let dir = tempfile::tempdir().unwrap();
        let dst = dir.path().join(format!("{}.zip", "a".repeat(246)));
        assert_eq!(dst.file_name().unwrap().len(), 250);
        write_atomic(&dst, b"zip").unwrap();
        assert_eq!(fs::read(&dst).unwrap(), b"zip");
    }

    #[test]
    fn temp_names_are_recognised_exactly() {
        assert!(is_temp_name(".kuma-tmp-123-0"));
        assert!(!is_temp_name("sample.kuma-tmp-notes.csv"));
        assert!(!is_temp_name(".kuma-tmp-notes.csv"));
        assert!(!is_temp_name(".kuma-tmp-1-2.csv"));
        assert!(!is_temp_name(".kuma-tmp-1-"));
        assert!(!is_temp_name(".backup.zip.kuma-tmp-1-0"));
    }
}
