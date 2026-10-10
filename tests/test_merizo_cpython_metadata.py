"""Offline-only boundaries for authenticated CI CPython metadata acquisition."""
from __future__ import annotations

from email.message import Message
import hashlib
import io
import json
from pathlib import Path
import tempfile
import traceback
import unittest
from unittest.mock import Mock, patch
import urllib.error
import urllib.request
import urllib.response
import zipfile

from scripts.merizo_runtime_archive import cpython_origin as origin

DUMMY_TOKEN = 'ghs_SYNTHETIC_OFFLINE_TEST_ONLY'
TAG = '3.11.9-9947079978'
METADATA_URLS = [origin.METADATA_ROOT + suffix for suffix in (
    'commits/main', 'releases/tags/' + TAG, 'commits/' + TAG)]


class Response(io.BytesIO):
    def __init__(self, url: str, raw: bytes = b'{}'):
        super().__init__(raw)
        self.url = url


class CPythonMetadataTests(unittest.TestCase):
    def test_exact_three_metadata_requests_are_authenticated_gets(self):
        calls = []

        def opened(request, *, timeout):
            calls.append(request)
            self.assertEqual(request.get_method(), 'GET')
            self.assertEqual(request.get_header('Authorization'), 'Bearer ' + DUMMY_TOKEN)
            self.assertNotIn('Authorization', request.headers)
            self.assertEqual(timeout, origin.NETWORK_OPERATION_SECONDS)
            return Response(request.full_url)

        opener = Mock(open=Mock(side_effect=opened))
        with patch.object(origin.urllib.request, 'build_opener', return_value=opener) as built:
            for url in METADATA_URLS:
                self.assertEqual(origin.fetch_metadata(url, github_token=DUMMY_TOKEN), b'{}')
        self.assertEqual([call.full_url for call in calls], METADATA_URLS)
        self.assertTrue(all(isinstance(call.args[0], origin._NoMetadataRedirects)
                            for call in built.call_args_list))

    def test_unapproved_urls_reject_before_constructing_authorization(self):
        suffix = '/repos/actions/python-versions/commits/main'
        rejected = [
            'http://api.github.com' + suffix,
            'https://API.GITHUB.COM' + suffix,
            'https://api.github.com:443' + suffix,
            'https://api.github.com:444' + suffix,
            'https://api.github.com:invalid' + suffix,
            'https://api.github.com.' + suffix,
            'https://api.github.com.attacker.invalid' + suffix,
            'https://user@api.github.com' + suffix,
            'https://user:password@api.github.com' + suffix,
            'https://api.github.com' + suffix + '?query=1',
            'https://api.github.com' + suffix + '?',
            'https://api.github.com' + suffix + '#fragment',
            'https://api.github.com' + suffix + '#',
            ' https://api.github.com' + suffix,
            'https://api.github.com' + suffix + '\n',
            'https://api.github.com/repos/other/python-versions/commits/main',
            'https://api.github.com/repos/actions/other/commits/main',
            origin.METADATA_ROOT + 'releases/latest',
            origin.METADATA_ROOT + 'releases/tags/',
            origin.METADATA_ROOT + 'releases/tags/../main',
            origin.METADATA_ROOT + 'commits/%2E%2E',
            origin.METADATA_ROOT + 'commits/tag%2Fbranch',
            origin.METADATA_ROOT + 'commits/tag/branch',
            origin.METADATA_ROOT + 'commits/' + 'a' * 129,
            'https://raw.githubusercontent.com/actions/python-versions/main/versions-manifest.json',
            'https://github.com/actions/python-versions/releases/download/' + TAG + '/python.zip',
            'https://www.python.org/ftp/python/3.11.9/Python-3.11.9.tar.xz',
        ]
        with patch.object(origin.urllib.request, 'Request') as request, \
             patch.object(origin.urllib.request, 'build_opener') as opener:
            for url in rejected:
                with self.subTest(url=url), self.assertRaisesRegex(ValueError, 'Unapproved.*endpoint'):
                    origin.fetch_metadata(url, github_token=DUMMY_TOKEN)
            request.assert_not_called()
            opener.assert_not_called()

    def test_redirect_targets_are_never_requested_even_on_same_origin(self):
        real_build_opener = urllib.request.build_opener
        for code in (301, 302, 303, 307, 308):
            for target in ('https://attacker.invalid/collect', METADATA_URLS[1]):
                calls = []

                class RedirectResponse(urllib.response.addinfourl):
                    msg = 'Synthetic redirect'

                class Transport(urllib.request.BaseHandler):
                    handler_order = 100

                    def https_open(self, req):
                        calls.append(req)
                        headers = Message()
                        headers['Location'] = target
                        return RedirectResponse(io.BytesIO(b''), headers, req.full_url, code)

                transport = Transport()
                with self.subTest(code=code, target=target), \
                     patch.object(origin.urllib.request, 'build_opener',
                                  side_effect=lambda *handlers: real_build_opener(*handlers, transport)), \
                     self.assertRaisesRegex(ValueError, 'redirects are forbidden'):
                    origin.fetch_metadata(METADATA_URLS[0], github_token=DUMMY_TOKEN)
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0].full_url, METADATA_URLS[0])

    def test_generic_fetch_never_has_an_authorization_header(self):
        urls = [
            'https://raw.githubusercontent.com/actions/python-versions/' + 'a' * 40 + '/versions-manifest.json',
            'https://github.com/actions/python-versions/releases/download/' + TAG + '/python.zip',
            'https://release-assets.githubusercontent.com/asset',
            'https://objects.githubusercontent.com/asset',
            'https://codeload.github.com/actions/python-versions/tar.gz/' + 'a' * 40,
            'https://www.python.org/ftp/python/3.11.9/Python-3.11.9.tar.xz',
            METADATA_URLS[0],
        ]
        calls = []

        def opened(request, *, timeout):
            calls.append(request)
            self.assertIsNone(request.get_header('Authorization'))
            self.assertNotIn(DUMMY_TOKEN, repr(request.header_items()))
            return Response(request.full_url)

        with patch.object(origin.urllib.request, 'urlopen', side_effect=opened):
            for url in urls:
                self.assertEqual(origin.fetch(url, 1024), b'{}')
        self.assertEqual(len(calls), len(urls))

    def test_http_failure_exposes_only_integer_status_without_retry_or_fallback(self):
        headers = Message()
        headers['Authorization'] = DUMMY_TOKEN
        exception = urllib.error.HTTPError(METADATA_URLS[0], 403,
                                          'Authorization: Bearer ' + DUMMY_TOKEN, headers, None)
        opener = Mock(open=Mock(side_effect=exception))
        with patch.object(origin.urllib.request, 'build_opener', return_value=opener), \
             patch.object(origin.urllib.request, 'urlopen') as fallback:
            try:
                origin.fetch_metadata(METADATA_URLS[0], github_token=DUMMY_TOKEN)
            except ValueError as exc:
                self.assertEqual(str(exc), 'CPython metadata request failed (HTTP 403)')
                self.assertNotIn(DUMMY_TOKEN, traceback.format_exc())
                self.assertTrue(exc.__suppress_context__)
            else:
                self.fail('HTTP failure was not rejected')
        opener.open.assert_called_once()
        fallback.assert_not_called()

    def test_transport_exception_echoing_request_cannot_leak_token(self):
        def opened(request, *, timeout):
            raise RuntimeError(repr(request.header_items()))

        with patch.object(origin.urllib.request, 'build_opener', return_value=Mock(open=opened)):
            try:
                origin.fetch_metadata(METADATA_URLS[0], github_token=DUMMY_TOKEN)
            except ValueError as exc:
                self.assertEqual(str(exc), 'CPython metadata request failed')
                self.assertNotIn(DUMMY_TOKEN, traceback.format_exc())
            else:
                self.fail('Transport exception was not rejected')

    def test_response_exception_echoing_token_cannot_leak_token(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.url = METADATA_URLS[0]
        response.read1.side_effect = RuntimeError(DUMMY_TOKEN)
        with patch.object(origin.urllib.request, 'build_opener',
                          return_value=Mock(open=Mock(return_value=response))):
            try:
                origin.fetch_metadata(METADATA_URLS[0], github_token=DUMMY_TOKEN)
            except ValueError:
                self.assertNotIn(DUMMY_TOKEN, traceback.format_exc())
            else:
                self.fail('Read exception was not rejected')

    def test_missing_or_invalid_token_fails_before_network_or_payload_creation(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(origin.urllib.request, 'build_opener') as opener:
            root = Path(directory)
            for token in (None, '', 'contains space', 'header\r\ninjection', 'x' * 4097):
                with self.subTest(token_length=len(token or '')), self.assertRaises(ValueError):
                    origin.acquire(root / 'record.json', root / 'payload', github_token=token)
                self.assertFalse((root / 'payload').exists())
                self.assertFalse((root / 'record.json').exists())
            opener.assert_not_called()

    def test_metadata_byte_bound_is_enforced(self):
        with patch.object(origin, 'MAX_METADATA', 1), \
             patch.object(origin.urllib.request, 'build_opener',
                          return_value=Mock(open=Mock(return_value=Response(METADATA_URLS[0])))), \
             self.assertRaisesRegex(ValueError, 'byte bound'):
            origin.fetch_metadata(METADATA_URLS[0], github_token=DUMMY_TOKEN)

    def test_expired_deadline_prevents_open(self):
        opener = Mock()
        with patch.object(origin.time, 'monotonic', return_value=301), \
             patch.object(origin.urllib.request, 'build_opener', return_value=opener), \
             self.assertRaisesRegex(TimeoutError, 'deadline exceeded'):
            origin.fetch_metadata(METADATA_URLS[0], github_token=DUMMY_TOKEN, deadline=300)
        opener.open.assert_not_called()

    def test_network_open_timeout_is_capped_by_remaining_budget(self):
        opener = Mock(open=Mock(return_value=Response(METADATA_URLS[0])))
        with patch.object(origin.time, 'monotonic', return_value=299.5), \
             patch.object(origin.urllib.request, 'build_opener', return_value=opener):
            origin.fetch_metadata(METADATA_URLS[0], github_token=DUMMY_TOKEN, deadline=300)
        self.assertEqual(opener.open.call_args.kwargs['timeout'], 0.5)

    def test_read1_checks_shared_deadline_before_and_after_each_chunk(self):
        for authenticated in (False, True):
            response = Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            response.url = METADATA_URLS[0]
            response.read1.return_value = b'a'
            with self.subTest(authenticated=authenticated), \
                 patch.object(origin.time, 'monotonic', side_effect=[298, 299, 301]), \
                 patch.object(origin.urllib.request, 'build_opener',
                              return_value=Mock(open=Mock(return_value=response))), \
                 patch.object(origin.urllib.request, 'urlopen', return_value=response), \
                 self.assertRaisesRegex(TimeoutError, 'deadline exceeded'):
                if authenticated:
                    origin.fetch_metadata(METADATA_URLS[0], github_token=DUMMY_TOKEN, deadline=300)
                else:
                    origin.fetch(METADATA_URLS[0], 1024, deadline=300)
            response.read1.assert_called_once_with(origin.NETWORK_CHUNK_BYTES)
            response.read.assert_not_called()

    def test_acquire_uses_exact_windows_candidate_and_auth_only_for_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record, requests, public_calls = self._acquire_fixture(root)
            self.assertEqual([request.full_url for request in requests], METADATA_URLS)
            self.assertEqual(len(public_calls), 4)
            self.assertEqual({deadline for _, deadline in public_calls}, {300})
            self.assertEqual(record['status'], 'candidate_bytes_unreviewed')
            self.assertEqual(record['manifest_commit'], 'a' * 40)
            self.assertEqual(record['provider_build_recipe']['commit'], 'b' * 40)
            self.assertEqual(len(record['binary_archive']['members']), 1)
            self.assertEqual(origin.verify(record), record)
            self.assertNotIn(DUMMY_TOKEN, (root / 'record.json').read_text())
            for path in (root / 'payload').iterdir():
                self.assertNotIn(DUMMY_TOKEN.encode(), path.read_bytes())

    def test_missing_or_ambiguous_candidate_never_picks_first(self):
        for machine, duplicate in (('', False), ('AMD64', True)):
            with self.subTest(machine=machine, duplicate=duplicate), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                with self.assertRaisesRegex(ValueError, 'Cannot uniquely identify'):
                    self._acquire_fixture(root, machine=machine, duplicate=duplicate)
                self.assertFalse((root / 'record.json').exists())
                self.assertEqual(list((root / 'payload').iterdir()), [])

    def _acquire_fixture(self, root, *, machine='AMD64', duplicate=False):
        filename = 'python-3.11.9-win32-x64.zip'
        binary_url = 'https://github.com/actions/python-versions/releases/download/' + TAG + '/' + filename
        asset = {'platform': 'win32', 'arch': 'x64', 'download_url': binary_url}
        manifest = [{'version': '3.11.9', 'files': [asset, {**asset, 'arch': 'x86'}]}]
        if duplicate:
            manifest[0]['files'].append(dict(asset))
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as zipped:
            zipped.writestr('python.exe', b'synthetic interpreter bytes')
        binary_bytes = archive.getvalue()
        metadata = {
            METADATA_URLS[0]: {'sha': 'a' * 40},
            METADATA_URLS[1]: {'assets': [{'name': filename, 'size': len(binary_bytes),
                                         'digest': 'sha256:' + hashlib.sha256(binary_bytes).hexdigest()}]},
            METADATA_URLS[2]: {'sha': 'b' * 40},
        }
        requests, public_calls = [], []

        def opened(request, *, timeout):
            requests.append(request)
            self.assertEqual(request.get_header('Authorization'), 'Bearer ' + DUMMY_TOKEN)
            return Response(request.full_url, json.dumps(metadata[request.full_url]).encode())

        def public_fetch(url, limit, destination=None, *, deadline=None):
            public_calls.append((url, deadline))
            if destination is None:
                self.assertEqual(url, 'https://raw.githubusercontent.com/actions/python-versions/' +
                                 'a' * 40 + '/versions-manifest.json')
                return json.dumps(manifest).encode()
            destination.write_bytes(binary_bytes if url == binary_url else b'synthetic source bytes')
            return b''

        with patch.object(origin.urllib.request, 'build_opener', return_value=Mock(open=opened)), \
             patch.object(origin, 'fetch', side_effect=public_fetch), \
             patch.object(origin.platform, 'python_version', return_value='3.11.9'), \
             patch.object(origin.platform, 'system', return_value='Windows'), \
             patch.object(origin.platform, 'machine', return_value=machine), \
             patch.object(origin.time, 'monotonic', return_value=0):
            record = origin.acquire(root / 'record.json', root / 'payload', github_token=DUMMY_TOKEN)
        return record, requests, public_calls


if __name__ == '__main__':
    unittest.main()
