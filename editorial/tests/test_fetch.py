from unittest import mock

from django.test import SimpleTestCase, TestCase

from editorial import fetch
from editorial.fetch import FetchError, canonical, hosts_for
from editorial.models import Source


class CanonicalTests(SimpleTestCase):
    def test_http_rejected(self):
        with self.assertRaises(FetchError):
            canonical('http://example.com/feed')

    def test_credentials_in_url_rejected(self):
        with self.assertRaises(FetchError):
            canonical('https://user:pass@example.com/feed')

    def test_custom_port_rejected(self):
        with self.assertRaises(FetchError):
            canonical('https://example.com:8443/feed')

    def test_credential_query_rejected(self):
        with self.assertRaises(FetchError):
            canonical('https://example.com/feed?token=abc123')

    def test_tracking_params_stripped_and_host_lowered(self):
        url = canonical('https://EXAMPLE.com/Feed?utm_source=x&fbclid=y&page=2')
        self.assertEqual(url, 'https://example.com/Feed?page=2')

    def test_empty_path_becomes_slash(self):
        self.assertEqual(canonical('https://example.com'), 'https://example.com/')


class HostsForTests(TestCase):
    def test_source_host_always_allowed(self):
        source = Source(name='S', kind='NEWS', url='https://news.example.com/feed')
        self.assertEqual(hosts_for(source), {'news.example.com'})

    def test_extra_hosts_added(self):
        source = Source(name='S', kind='NEWS', url='https://news.example.com/feed',
                        allowed_hosts='apply.example.org\n')
        self.assertEqual(hosts_for(source), {'news.example.com', 'apply.example.org'})

    def test_wildcard_rejected(self):
        source = Source(name='S', kind='NEWS', url='https://news.example.com/feed',
                        allowed_hosts='*.example.com')
        with self.assertRaises(FetchError):
            hosts_for(source)

    def test_host_with_path_rejected(self):
        source = Source(name='S', kind='NEWS', url='https://news.example.com/feed',
                        allowed_hosts='example.com/path')
        with self.assertRaises(FetchError):
            hosts_for(source)


class PublicAddressTests(SimpleTestCase):
    def _addrinfo(self, ip):
        return [(None, None, None, None, (ip, 443))]

    def test_public_ip_ok(self):
        with mock.patch.object(fetch.socket, 'getaddrinfo', return_value=self._addrinfo('93.184.216.34')):
            self.assertEqual(fetch.public_addresses('example.com'), ['93.184.216.34'])

    def test_private_ip_rejected(self):
        with mock.patch.object(fetch.socket, 'getaddrinfo', return_value=self._addrinfo('10.0.0.5')):
            with self.assertRaises(FetchError):
                fetch.public_addresses('example.com')

    def test_loopback_rejected(self):
        with mock.patch.object(fetch.socket, 'getaddrinfo', return_value=self._addrinfo('127.0.0.1')):
            with self.assertRaises(FetchError):
                fetch.public_addresses('localhost')

    def test_dns_failure(self):
        with mock.patch.object(fetch.socket, 'getaddrinfo', side_effect=OSError('nope')):
            with self.assertRaises(FetchError):
                fetch.public_addresses('missing.example.com')


class FakeResponse:
    def __init__(self, status=200, body=b'hello', headers=None):
        self.status = status
        self._body = body
        self._headers = headers or {}

    def getheader(self, name):
        return self._headers.get(name)

    def read1(self, n):
        body, self._body = self._body, b''
        return body


class FakeConn:
    responses = []

    def __init__(self, host, ip):
        self.host = host

    def request(self, method, path, headers=None):
        pass

    def getresponse(self):
        return FakeConn.responses.pop(0)

    def close(self):
        pass


class FetchTests(SimpleTestCase):
    def setUp(self):
        FakeConn.responses = []
        patchers = [
            mock.patch.object(fetch, 'PinnedHTTPS', FakeConn),
            mock.patch.object(fetch, 'public_addresses', return_value=['93.184.216.34']),
        ]
        for p in patchers:
            p.start()
            self.addCleanup(p.stop)

    def test_unapproved_host_rejected_before_network(self):
        with self.assertRaises(FetchError) as ctx:
            fetch.fetch('https://other.example.com/x', {'example.com'})
        self.assertEqual(str(ctx.exception), 'host_not_approved')

    def test_ok_response(self):
        FakeConn.responses = [FakeResponse(200, b'body-text')]
        status, body, url = fetch.fetch('https://example.com/page', {'example.com'})
        self.assertEqual((status, body), (200, b'body-text'))

    def test_redirect_followed_within_allowed_hosts(self):
        FakeConn.responses = [
            FakeResponse(302, b'', {'Location': 'https://example.com/final'}),
            FakeResponse(200, b'final-body'),
        ]
        status, body, url = fetch.fetch('https://example.com/start', {'example.com'})
        self.assertEqual(body, b'final-body')
        self.assertEqual(url, 'https://example.com/final')

    def test_redirect_to_unapproved_host_rejected(self):
        FakeConn.responses = [FakeResponse(302, b'', {'Location': 'https://evil.example.net/x'})]
        with self.assertRaises(FetchError):
            fetch.fetch('https://example.com/start', {'example.com'})

    def test_oversized_response_rejected(self):
        FakeConn.responses = [FakeResponse(200, b'x' * (fetch.MAX_BYTES + 10))]
        with self.assertRaises(FetchError):
            fetch.fetch('https://example.com/big', {'example.com'})


class ReadableTests(SimpleTestCase):
    def test_scripts_nav_and_forms_stripped(self):
        html = b'<html><body><nav>NAV</nav><script>var x=1;</script><p>Hello <b>Kebbi</b></p><form><p>FORM</p></form></body></html>'
        text = fetch.readable(html)
        self.assertIn('Hello Kebbi', text)
        self.assertNotIn('NAV', text)
        self.assertNotIn('FORM', text)

    def test_application_links_detected(self):
        html = b'<html><body><a href="https://example.com/apply">Apply now</a><a href="https://example.com/about">About us</a></body></html>'
        links = fetch.application_links(html, 'https://example.com/news')
        self.assertEqual([l['url'] for l in links], ['https://example.com/apply'])
