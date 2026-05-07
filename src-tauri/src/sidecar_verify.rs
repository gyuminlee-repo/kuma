/// sidecar_verify.rs
///
/// Build-time SHA-256 hash verification for sidecar binaries.
///
/// In debug builds (`cfg!(debug_assertions)`), all checks are bypassed so
/// developers do not need to regenerate hashes on every recompile.
///
/// In release builds, `verify_sidecar` computes the SHA-256 of the binary at
/// `path` and compares it against `expected_hash`. A mismatch causes the
/// sidecar spawn to be aborted.
use sha2::{Digest, Sha256};
use std::{
    fs::File,
    io::{self, Read},
    path::Path,
};

/// Read a file in 64 KiB chunks and compute its SHA-256.
fn sha256_file(path: &Path) -> io::Result<String> {
    let mut file = File::open(path)?;
    let mut hasher = Sha256::new();
    let mut buf = vec![0u8; 65536];
    loop {
        let n = file.read(&mut buf)?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
    }
    Ok(format!("{:x}", hasher.finalize()))
}

/// Verify the binary at `path` matches `expected_hash` (hex SHA-256).
///
/// Returns `Ok(())` on success or when running in a debug build.
/// Returns `Err(message)` on hash mismatch or I/O failure in release builds.
pub fn verify_sidecar(path: &Path, expected_hash: &str) -> Result<(), String> {
    // Dev-mode bypass: skip verification entirely to avoid forcing developers
    // to regenerate hashes after every incremental Python change.
    if cfg!(debug_assertions) {
        return Ok(());
    }

    let actual = sha256_file(path).map_err(|e| {
        format!(
            "sidecar hash check failed — cannot read {}: {}",
            path.display(),
            e
        )
    })?;

    if actual != expected_hash {
        Err(format!(
            "sidecar binary integrity check failed for {}\n  expected: {}\n  actual:   {}",
            path.display(),
            expected_hash,
            actual,
        ))
    } else {
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::NamedTempFile;

    /// Helper: SHA-256 of an in-memory byte slice (for test assertions).
    fn sha256_bytes(data: &[u8]) -> String {
        let mut hasher = Sha256::new();
        hasher.update(data);
        format!("{:x}", hasher.finalize())
    }

    #[test]
    fn sha256_file_matches_in_memory() {
        let content = b"hello sidecar integrity";
        let mut tmp = NamedTempFile::new().expect("tmpfile");
        tmp.write_all(content).unwrap();
        let computed = sha256_file(tmp.path()).unwrap();
        let expected = sha256_bytes(content);
        assert_eq!(computed, expected);
    }

    #[test]
    fn verify_sidecar_passes_on_correct_hash() {
        // In debug builds verify_sidecar always passes, so this test is
        // effectively a no-op in CI. In release it exercises the real path.
        let content = b"sidecar binary content";
        let mut tmp = NamedTempFile::new().expect("tmpfile");
        tmp.write_all(content).unwrap();
        let hash = sha256_bytes(content);
        // Should succeed regardless of build mode (debug: bypass; release: match)
        assert!(verify_sidecar(tmp.path(), &hash).is_ok());
    }

    /// This test only runs in release builds where verification is active.
    #[test]
    #[cfg(not(debug_assertions))]
    fn verify_sidecar_rejects_wrong_hash() {
        let content = b"sidecar binary content";
        let mut tmp = NamedTempFile::new().expect("tmpfile");
        tmp.write_all(content).unwrap();
        let result = verify_sidecar(tmp.path(), "deadbeef");
        assert!(result.is_err());
        let msg = result.unwrap_err();
        assert!(msg.contains("integrity check failed"));
    }
}
