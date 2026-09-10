# Throwaway CA fixtures for the operator CA tests

Two self-signed certificates used by `tests/shared/test_net_ssl_context.py` to
check that `kuma_core.shared.net` loads an operator-supplied CA bundle into its
SSL context.

| File | Subject / issuer CN | Read by |
|---|---|---|
| `throwaway_test_only_ca_proxy.crt` | `kuma-test-proxy-ca` | every test that reaches the CA through `KURO_CA_BUNDLE`, including the two that assert the CN |
| `throwaway_test_only_ca_config.crt` | `kuma-config-ca` | `test_operator_ca_from_config_is_loaded`, via `ca_bundle` in `~/.kuma/kuro/config.json` |

Two files rather than one is inherited from an earlier revision in which each
of those tests asserted its own CN. Today only `kuma-test-proxy-ca` is asserted
by name; the config fixture shows only that the config key reaches
`load_verify_locations`, which is worth checking on its own because that key
takes a different route through `operator_ca_bundle()` than the environment
variable does. Keeping the two files distinct costs nothing and stops the two
sources from sharing a subject, which would leave a CN assertion unable to say
which source the certificate came from.

## These are not credentials

Neither file is a secret, and neither is in use anywhere.

- Each holds a single `-----BEGIN CERTIFICATE-----` block and nothing else. The
  RSA private key was written to `/dev/null` at mint time and never existed on
  disk, so these certificates can sign nothing. `grep -c PRIVATE` returns 0 for
  both.
- Neither is trusted by anything that ships. They are read only by the test
  file above, which points `KURO_CA_BUNDLE` (or a temporary `HOME`) at them.
- No test performs a TLS handshake or verifies any real connection with them.
  The module docstring of `test_net_ssl_context.py` states that scope directly:
  proving the context verifies a re-signed connection needs a live proxy and is
  out of scope there. The assertions here cover loading alone: that
  `operator_ca_status()` reports `"loaded"`, and that the CN is present in the
  store of the context built on a fallback tier. Membership is read there
  rather than on the shared context because a `truststore` context raises
  `NotImplementedError` from `get_ca_certs()`; the tier-1 case reads the plain
  context it wraps, and skips if that private attribute ever goes away.
- The CNs (`kuma-test-proxy-ca`, `kuma-config-ca`) name no real certificate
  authority. The institutional inspection proxy that motivated the operator
  CA escape hatch presents `CN=ePrism SSL, O=SOOSAN INT, C=KR`, which appears nowhere here.

## How these were generated

OpenSSL 3.0.13 (30 Jan 2024). Run from the repository root:

```
openssl req -x509 -newkey rsa:2048 -nodes -keyout /dev/null -sha256 -days 3650 \
  -subj '/CN=kuma-test-proxy-ca' -addext 'basicConstraints=critical,CA:TRUE' \
  -out tests/fixtures/net/throwaway_test_only_ca_proxy.crt

openssl req -x509 -newkey rsa:2048 -nodes -keyout /dev/null -sha256 -days 3650 \
  -subj '/CN=kuma-config-ca' -addext 'basicConstraints=critical,CA:TRUE' \
  -out tests/fixtures/net/throwaway_test_only_ca_config.crt
```

`-keyout /dev/null` is the point of the command rather than a shortcut: it
discards the key that signed the certificate.

Regenerating produces a different key, serial number, and validity window, so
the committed bytes will not match. That is fine. Only two properties are
load-bearing.

- **The CN must stay as it is**, since the tests assert on that exact string.
- **`basicConstraints` must be `CA:TRUE`.** A certificate minted without it
  still loads without raising, so `operator_ca_status()` would still report
  `"loaded"`, but OpenSSL filters it out of `ctx.get_ca_certs()`, so the CN
  assertion in the membership tests fails with no obvious cause. The flag is
  passed explicitly rather than left to an OpenSSL default for that reason.

Expiry is not load-bearing. `load_verify_locations` accepts an expired CA
without complaint (measured on OpenSSL 3.0.13 and 3.5.5: an already expired
certificate loads, raises nothing, and appears in the store of a plain
context), so these
fixtures do not become a time bomb in 2036. The ten year window is there to
keep them plausible on inspection, not to keep the tests passing.

Verification command for a regenerated fixture:

```
openssl x509 -in tests/fixtures/net/throwaway_test_only_ca_proxy.crt \
  -noout -subject -issuer -dates -ext basicConstraints
```

## Why the extension is `.crt`

The ignore file excludes `*.pem` and `*.key` across the whole repository, which
is a guard worth keeping absolute. Naming these `.crt` keeps them tracked
without adding a negation that would open a hole under this directory for real
certificates later. The file content is ordinary PEM either way, and
`ssl.SSLContext.load_verify_locations` does not look at the extension.

## Why static files rather than minting at test time

The tests previously minted a CA in-process with the `cryptography` package and
skipped when it was absent. That package is in neither the core dependencies
nor the `test` extra of `pyproject.toml`, so it is missing from the Python 3.11
build interpreter and from every CI job, all of which install with
`pip install -e ".[test]"`. Both tests therefore skipped everywhere, leaving the
operator CA path, the only trust leg that keeps a frozen macOS build working on
an inspecting network, with no automated coverage at all. Static fixtures need
no dependency and run on any interpreter.
