"""Shared network helpers for SSL context creation (frozen-safe, cross-platform)."""
from __future__ import annotations

import json
import logging
import os
import ssl
from typing import Iterator

from .config_paths import kuma_home

_log = logging.getLogger(__name__)

#: Environment variable holding a path to an extra PEM CA bundle.
CA_BUNDLE_ENV = "KURO_CA_BUNDLE"
#: Key in ~/.kuma/kuro/config.json holding the same path.
CA_BUNDLE_CONFIG_KEY = "ca_bundle"

#: Operator-facing explanation for a certificate verification failure.
#:
#: Ordered by what actually fixes it. kuma verifies against the operating
#: system trust store first, so installing the CA there fixes every tool on
#: the machine at once; the bundle path below is the fallback for a site that
#: cannot change the OS store.
TLS_REMEDY = (
    "TLS certificate verification failed. This network may run a TLS inspection "
    "proxy whose CA kuma does not trust. Install that CA in the operating system "
    "trust store (macOS Keychain, the Windows certificate store, or "
    "update-ca-certificates on Linux). If that is not possible, export the CA as "
    f"a PEM file and set {CA_BUNDLE_ENV}=<path> or add "
    f"\"{CA_BUNDLE_CONFIG_KEY}\": \"<path>\" to ~/.kuma/kuro/config.json. "
    "Restart kuma afterwards."
)

_ssl_ctx: ssl.SSLContext | None = None
_ssl_ctx_source: str | None = None
_operator_ca_status: str = "absent"


def _config_ca_bundle() -> str:
    """Read ``ca_bundle`` from the KURO sidecar config, or "" if unavailable.

    Mirrors ``sidecar_kuro.core._get_config`` (same file, same swallow-and-
    continue behaviour) rather than importing it, because ``kuma_core`` must not
    depend on the ``python-core`` adapters.
    """
    path = kuma_home() / "kuro" / "config.json"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(loaded, dict):
        return ""
    return str(loaded.get(CA_BUNDLE_CONFIG_KEY, "") or "").strip()


def operator_ca_bundle() -> str:
    """Resolve the operator-supplied CA path. Env var wins over config.

    ``~`` is expanded, since an operator typing the path by hand into either
    source writes it that way and OpenSSL would otherwise report a missing file.
    """
    env_value = os.environ.get(CA_BUNDLE_ENV, "").strip()
    raw = env_value or _config_ca_bundle()
    return os.path.expanduser(raw) if raw else ""


def _load_operator_ca(ctx: ssl.SSLContext) -> None:
    """Add the operator-supplied CA to ``ctx``, whichever tier built it.

    ``load_verify_locations`` adds to a context rather than replacing what it
    holds, so this costs the tier-1 store nothing: a truststore context that
    has been handed an extra CA still verifies everything the platform trusts.

    Its failures are caught here, narrowly, and never demote a tier. A bad
    path raises ``FileNotFoundError`` and a malformed PEM raises ``SSLError``;
    if either were allowed to escape into the tier-1 ``except Exception`` the
    result would be a silent fall back to certifi, which is exactly the tier
    that cannot verify an inspected network.
    """
    global _operator_ca_status
    ca_path = operator_ca_bundle()
    if not ca_path:
        _operator_ca_status = "absent"
        return
    try:
        ctx.load_verify_locations(cafile=ca_path)
    except Exception as exc:  # noqa: BLE001 - never demote a tier over this
        _operator_ca_status = "failed"
        _log.warning(
            "Operator CA bundle %s could not be loaded (%s: %s); continuing without it",
            ca_path,
            type(exc).__name__,
            exc,
        )
    else:
        _operator_ca_status = "loaded"
        _log.info("Operator CA bundle loaded from %s", ca_path)


def get_ssl_context() -> ssl.SSLContext:
    """Cached SSL context, preferring the operating system trust store.

    Three tiers, in order:

    1. ``truststore`` - delegates verification to the platform native API
       (macOS Security framework, Windows CryptoAPI, OpenSSL on Linux). This
       tier exists because both failure modes below are trust-store problems,
       not bundle problems:

       * macOS frozen apps: the system OpenSSL does not read the Keychain and
         the build-machine CA store is absent, so every outbound HTTPS call
         fails with CERTIFICATE_VERIFY_FAILED.
       * Managed networks (corporate/institutional TLS-inspecting proxies):
         the proxy re-signs traffic with a private root that is installed in
         the OS store only.

    2. ``certifi`` - the bundled cacert.pem. This was the previous sole
       behaviour (commit 54a84838). It fixed the macOS frozen case but broke
       every TLS-inspected network, because a proxy root lives in the OS store
       and can never be in certifi. Keep it only as a fallback, and do not
       promote it back to tier 1.

    3. stdlib default - last resort when neither package is importable
       (bare-environment testing).

    Tier 1 failures are caught broadly on purpose: in a frozen bundle
    truststore loads the native API through ``ctypes``, so a missing or
    unloadable system library raises ``OSError``/``ImportError`` rather than
    ``ModuleNotFoundError``. Falling through then leaves behaviour no worse
    than tier 2, which is what shipped before.

    Whichever tier wins is then handed the operator-supplied CA bundle, if one
    is configured (:data:`CA_BUNDLE_ENV` or :data:`CA_BUNDLE_CONFIG_KEY`).
    That step is additive rather than a fourth tier, and it stays outside the
    tier-1 ``except`` so that a mistyped path cannot silently demote a working
    truststore context to certifi. It is the only recourse left on a site whose
    proxy root is in neither the OS store nor certifi, and it is what keeps the
    tier-2 fallback usable on an inspected network.

    Scope note: this only covers *context construction*. A verification
    failure that happens at handshake time surfaces at the call site, not
    here; :func:`describe_tls_error` turns such a failure into the operator
    advice in :data:`TLS_REMEDY`.

    ``get_ssl_context_source()`` reports which tier was taken, and
    ``operator_ca_status()`` whether the extra bundle was applied, so the same
    problem does not have to be re-diagnosed from a stack trace next time.
    """
    global _ssl_ctx, _ssl_ctx_source
    if _ssl_ctx is None:
        # ctx is annotated so the type checker keeps a concrete return type
        # even where truststore is not installed in the analysis environment
        # and its SSLContext subclass resolves as Unknown.
        ctx: ssl.SSLContext
        try:
            import truststore

            ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            source = "truststore"
        except Exception as exc:  # noqa: BLE001 - see docstring on ctypes failures
            # Log why tier 1 was skipped, otherwise a silent demotion to the
            # certifi bundle looks identical to the bug this replaced.
            _log.info("truststore unavailable (%s: %s)", type(exc).__name__, exc)
            try:
                import certifi

                ctx = ssl.create_default_context(cafile=certifi.where())
                source = "certifi"
            except ModuleNotFoundError:
                ctx = ssl.create_default_context()
                source = "stdlib"
        _load_operator_ca(ctx)
        _ssl_ctx = ctx
        _ssl_ctx_source = source
        _log.info(
            "SSL context trust source: %s (operator CA: %s)",
            source,
            _operator_ca_status,
        )
    return _ssl_ctx


def get_ssl_context_source() -> str | None:
    """Return which trust source :func:`get_ssl_context` used, or None if unused."""
    return _ssl_ctx_source


def operator_ca_status() -> str:
    """Whether the operator CA bundle was applied to the cached context.

    ``"absent"`` before any context is built and when no path is configured,
    ``"loaded"`` once one was added, ``"failed"`` when a path was configured
    but could not be read. The third state is the one that matters: it is how
    an operator tells "my bundle is in use" from "my bundle was ignored".
    """
    return _operator_ca_status


def reset_ssl_context() -> None:
    """Drop the cached context and its provenance so the next call rebuilds."""
    global _ssl_ctx, _ssl_ctx_source, _operator_ca_status
    _ssl_ctx = None
    _ssl_ctx_source = None
    _operator_ca_status = "absent"


def _exception_chain(exc: BaseException) -> Iterator[BaseException]:
    """Yield exc and everything it wraps (``reason``, ``__cause__``, ``__context__``)."""
    seen: set[int] = set()
    stack: list[BaseException | None] = [exc]
    while stack:
        node = stack.pop()
        if node is None or id(node) in seen:
            continue
        seen.add(id(node))
        yield node
        reason = getattr(node, "reason", None)
        stack.append(reason if isinstance(reason, BaseException) else None)
        stack.append(node.__cause__)
        stack.append(node.__context__)


def describe_tls_error(exc: BaseException) -> str | None:
    """Return :data:`TLS_REMEDY` when ``exc`` is a CA verification failure.

    urllib wraps ``ssl.SSLCertVerificationError`` inside ``URLError``, so the
    whole chain is walked before falling back to a string match. truststore
    raises that same exception type on all three platforms, so the unwrap holds
    whichever tier built the context.
    """
    for node in _exception_chain(exc):
        if isinstance(node, ssl.SSLCertVerificationError):
            return TLS_REMEDY
    if "CERTIFICATE_VERIFY_FAILED" in str(exc):
        return TLS_REMEDY
    return None
