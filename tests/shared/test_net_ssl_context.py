"""Tests for kuma_core.shared.net: trust tiering, the operator CA, TLS advice.

None of these touch the network. Proving that the context actually verifies a
re-signed connection needs a live proxy and is out of scope here.

The operator CA tests read two checked-in throwaway certificates from
tests/fixtures/net/ rather than minting one in-process. See the README there for
provenance and for why committing them is safe.

Three assertions that an earlier revision of this file carried are gone rather
than weakened, because their subject no longer exists:

* ``test_steps_are_recorded_and_never_shrink`` read a per-step certificate
  count. Trust is no longer assembled step by step out of an OS-store context
  plus certifi, so there are no steps and no counts.
* ``test_context_is_a_superset_of_os_store_and_certifi`` and
  ``test_context_has_more_certificates_than_certifi_alone`` compared
  ``get_ca_certs()`` on the shared context. A truststore context raises
  ``NotImplementedError`` from both ``get_ca_certs`` and ``cert_store_stats``
  (measured, ``truststore/_api.py``), so those reads go blind on exactly the
  tier that is working, and the superset claim is now deliberately false:
  certifi is not loaded onto tier 1. The claim they stood for, that kuma does
  better than certifi alone on an inspected network, is carried by
  ``get_ssl_context_source() == "truststore"`` plus the live probe recorded in
  the commit that introduced the tiering.
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error

import pytest

from kuma_core.shared import net


@pytest.fixture(autouse=True)
def _isolated_context(monkeypatch, tmp_path):
    """Every test starts from a cold cache and an empty ~/.kuma."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv(net.CA_BUNDLE_ENV, raising=False)
    net.reset_ssl_context()
    yield
    net.reset_ssl_context()


#: Checked-in throwaway CA certificates. See the README beside them.
_CA_FIXTURE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures", "net"
)


def _throwaway_ca(filename):
    """Path to a committed throwaway CA certificate.

    Static rather than minted in-process, so these tests need no cryptography
    package and therefore run on the Python 3.11 build interpreter and in CI,
    neither of which installs one. What the files are, why committing them is
    safe (self-signed, private key discarded at mint time, trusted by nothing
    that ships), and the exact command that regenerates them are documented in
    tests/fixtures/net/README.md.
    """
    path = os.path.join(_CA_FIXTURE_DIR, filename)
    assert os.path.isfile(path), (
        f"missing CA fixture {path}; regenerate it with the command in "
        "tests/fixtures/net/README.md"
    )
    return path


def _subject_common_names(ctx):
    names = set()
    for cert in ctx.get_ca_certs():
        for rdn in cert.get("subject", ()):
            for key, value in rdn:
                if key == "commonName":
                    names.add(value)
    return names


def _without(monkeypatch, *module_names):
    """Make ``import <name>`` raise ModuleNotFoundError inside get_ssl_context."""
    for name in module_names:
        monkeypatch.setitem(sys.modules, name, None)
    net.reset_ssl_context()


# --- tier selection ---------------------------------------------------------


def test_tier_one_is_truststore():
    """Nothing else pins that the OS trust store tier is the one actually taken."""
    pytest.importorskip("truststore")
    net.get_ssl_context()
    assert net.get_ssl_context_source() == "truststore"


def test_falls_back_to_certifi_when_truststore_unavailable(monkeypatch):
    pytest.importorskip("certifi")
    _without(monkeypatch, "truststore")

    ctx = net.get_ssl_context()

    assert net.get_ssl_context_source() == "certifi"
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


def test_stdlib_tier_when_neither_package_is_importable(monkeypatch):
    ca_path = _throwaway_ca("throwaway_test_only_ca_proxy.crt")
    monkeypatch.setenv(net.CA_BUNDLE_ENV, ca_path)
    _without(monkeypatch, "truststore", "certifi")

    ctx = net.get_ssl_context()

    assert net.get_ssl_context_source() == "stdlib"
    assert net.operator_ca_status() == "loaded"
    assert ctx.verify_mode == ssl.CERT_REQUIRED


# --- operator-supplied CA ---------------------------------------------------


def test_operator_ca_from_env_is_loaded(monkeypatch):
    ca_path = _throwaway_ca("throwaway_test_only_ca_proxy.crt")
    monkeypatch.setenv(net.CA_BUNDLE_ENV, ca_path)
    net.reset_ssl_context()

    ctx = net.get_ssl_context()

    assert isinstance(ctx, ssl.SSLContext)
    assert net.operator_ca_status() == "loaded"


def test_operator_ca_from_config_is_loaded(tmp_path):
    ca_path = _throwaway_ca("throwaway_test_only_ca_config.crt")
    config = tmp_path / "home" / ".kuma" / "kuro" / "config.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps({net.CA_BUNDLE_CONFIG_KEY: ca_path}), encoding="utf-8")

    assert net.operator_ca_bundle() == ca_path
    net.get_ssl_context()
    assert net.operator_ca_status() == "loaded"


def test_operator_ca_reaches_the_store_on_the_fallback_tier(monkeypatch):
    """Membership evidence, read off a plain context that can be inspected."""
    ca_path = _throwaway_ca("throwaway_test_only_ca_proxy.crt")
    monkeypatch.setenv(net.CA_BUNDLE_ENV, ca_path)
    _without(monkeypatch, "truststore")

    ctx = net.get_ssl_context()

    assert net.operator_ca_status() == "loaded"
    assert "kuma-test-proxy-ca" in _subject_common_names(ctx)


def test_operator_ca_reaches_the_inner_store_on_truststore(monkeypatch):
    """The only automated evidence that layering reaches tier 1 itself.

    A truststore context refuses ``get_ca_certs``, so the assertion has to read
    the plain context it wraps. ``_ctx`` is private to a floor-pinned
    dependency (``truststore>=0.10.4``), so an upstream rename must skip rather
    than turn CI red on a build that works.
    """
    pytest.importorskip("truststore")
    ca_path = _throwaway_ca("throwaway_test_only_ca_proxy.crt")
    monkeypatch.setenv(net.CA_BUNDLE_ENV, ca_path)
    net.reset_ssl_context()

    ctx = net.get_ssl_context()
    assert net.get_ssl_context_source() == "truststore"
    assert net.operator_ca_status() == "loaded"

    inner = getattr(ctx, "_ctx", None)
    if inner is None:
        pytest.skip("truststore no longer exposes the wrapped context as _ctx")
    assert "kuma-test-proxy-ca" in _subject_common_names(inner)


def test_env_wins_over_config(monkeypatch, tmp_path):
    config = tmp_path / "home" / ".kuma" / "kuro" / "config.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        json.dumps({net.CA_BUNDLE_CONFIG_KEY: "/from/config.pem"}), encoding="utf-8"
    )
    monkeypatch.setenv(net.CA_BUNDLE_ENV, "/from/env.pem")

    assert net.operator_ca_bundle() == "/from/env.pem"


def test_tilde_in_operator_ca_path_is_expanded(monkeypatch, tmp_path):
    monkeypatch.setenv(net.CA_BUNDLE_ENV, "~/proxy-ca.pem")
    assert net.operator_ca_bundle() == str(tmp_path / "home" / "proxy-ca.pem")


# --- degradation ------------------------------------------------------------


def test_missing_operator_ca_does_not_raise(monkeypatch, tmp_path):
    monkeypatch.setenv(net.CA_BUNDLE_ENV, str(tmp_path / "no-such-ca.pem"))
    net.reset_ssl_context()

    ctx = net.get_ssl_context()

    assert isinstance(ctx, ssl.SSLContext)
    assert net.operator_ca_status() == "failed"
    # The bad path must not cost the tier: swallowing it inside the tier-1
    # except would demote a working OS-store context to certifi, which is the
    # tier that cannot verify an inspected network.
    if "truststore" in sys.modules and sys.modules["truststore"] is not None:
        assert net.get_ssl_context_source() == "truststore"


def test_malformed_operator_ca_does_not_raise(monkeypatch, tmp_path):
    bad = tmp_path / "garbage.pem"
    bad.write_text("this is not a certificate\n", encoding="utf-8")
    monkeypatch.setenv(net.CA_BUNDLE_ENV, str(bad))
    net.reset_ssl_context()

    ctx = net.get_ssl_context()

    assert isinstance(ctx, ssl.SSLContext)
    assert net.operator_ca_status() == "failed"
    if "truststore" in sys.modules and sys.modules["truststore"] is not None:
        assert net.get_ssl_context_source() == "truststore"


def test_unreadable_config_is_ignored(tmp_path):
    config = tmp_path / "home" / ".kuma" / "kuro" / "config.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("{not json", encoding="utf-8")

    assert net.operator_ca_bundle() == ""
    assert isinstance(net.get_ssl_context(), ssl.SSLContext)


# --- caching ----------------------------------------------------------------


def test_context_is_cached_until_reset():
    first = net.get_ssl_context()
    assert net.get_ssl_context() is first
    assert net.get_ssl_context_source() is not None

    net.reset_ssl_context()

    assert net.get_ssl_context_source() is None, "reset left a stale trust source"
    assert net.operator_ca_status() == "absent"
    assert net.get_ssl_context() is not first


# --- error advice -----------------------------------------------------------


def test_describe_tls_error_unwraps_urlerror():
    verify_error = ssl.SSLCertVerificationError(
        "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
        "unable to get local issuer certificate"
    )
    wrapped = urllib.error.URLError(verify_error)

    message = net.describe_tls_error(wrapped)
    assert message is not None
    assert message == net.TLS_REMEDY
    assert net.CA_BUNDLE_ENV in message
    assert "inspection proxy" in message


def test_remedy_names_the_os_store_before_the_bundle():
    """The tiering made the OS store the fix and the bundle the fallback."""
    remedy = net.TLS_REMEDY
    assert "certificate verification failed" in remedy, (
        "the frontend classifier matches on 'certificate verif'; keep that "
        "wording so the remedy classifies as a network error on its own"
    )
    assert remedy.index("trust store") < remedy.index(net.CA_BUNDLE_ENV)


def test_describe_tls_error_matches_string_only_form():
    opaque = RuntimeError(
        "<urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed>"
    )
    assert net.describe_tls_error(opaque) == net.TLS_REMEDY


def test_describe_tls_error_ignores_unrelated_failures():
    assert net.describe_tls_error(TimeoutError("timed out")) is None
    assert net.describe_tls_error(urllib.error.URLError("connection refused")) is None
