"""Tests for the scraper's HTTP client: connection reuse, redirect checks, size caps.

Uses a fake connection, so no network is needed.

Run with: .venv/bin/python -m unittest discover -s tests
"""

import http.client
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import scrape  # noqa: E402

HOST = 'www.uni-marburg.de'
BASE = f'https://{HOST}'
REASONS = {200: 'OK', 301: 'Moved Permanently', 302: 'Found', 403: 'Forbidden'}


class FakeResponse:
    def __init__(self, status, body=b'', headers=None):
        self.status = status
        self.reason = REASONS.get(status, '')
        self._body = body
        self._headers = headers or {}

    def getheader(self, name, default=None):
        return self._headers.get(name, default)

    def read(self, amt=None):
        data = self._body if amt is None else self._body[:amt]
        self._body = self._body[len(data):]
        return data

    def isclosed(self):
        return not self._body


class FakeSocket:
    def settimeout(self, timeout):
        pass


class FakeConnection:
    """Serves responses from `routes` (path -> FakeResponse, or an exception to raise)."""

    def __init__(self, server, host):
        self.server = server
        self.host = host
        self.sock = None
        self.timeout = None
        self.closed = False
        self.requests = []

    def request(self, method, target, headers=None):
        self.sock = self.sock or FakeSocket()
        self.requests.append(target)
        self._target = target

    def getresponse(self):
        answer = self.server.answer(self, self._target)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def close(self):
        self.sock = None
        self.closed = True


class FakeServer:
    def __init__(self, routes):
        self.routes = routes  # path -> FakeResponse factory, or a list consumed in order
        self.connections = []

    def connect(self, host, port, timeout):
        conn = FakeConnection(self, host)
        self.connections.append(conn)
        return conn

    def answer(self, conn, target):
        route = self.routes[target]
        if isinstance(route, list):
            route = route.pop(0)
        return route() if callable(route) else route


def ok(body=b'%PDF data'):
    return lambda: FakeResponse(200, body)


def redirect(location, status=302):
    return lambda: FakeResponse(status, b'', {'Location': location})


class Client(unittest.TestCase):
    def client(self, routes):
        self.server = FakeServer(routes)
        return scrape.KeepAliveClient(connect=self.server.connect)

    def test_reuses_one_connection_for_many_requests(self):
        client = self.client({'/a.pdf': ok(b'A'), '/b.pdf': ok(b'B')})
        self.assertEqual(client.get(f'{BASE}/a.pdf', 30, 100), b'A')
        self.assertEqual(client.get(f'{BASE}/b.pdf', 30, 100), b'B')
        self.assertEqual(len(self.server.connections), 1)
        self.assertEqual(self.server.connections[0].requests, ['/a.pdf', '/b.pdf'])

    def test_sends_query_string(self):
        client = self.client({'/a.pdf?x=1': ok(b'A')})
        self.assertEqual(client.get(f'{BASE}/a.pdf?x=1', 30, 100), b'A')

    def test_refuses_non_university_url_without_connecting(self):
        client = self.client({})
        for url in ('https://example.org/a.pdf', f'http://{HOST}/a.pdf',
                    'https://uni-marburg.de.example.org/a.pdf', 'file:///etc/passwd'):
            with self.assertRaisesRegex(ValueError, 'non-university'):
                client.get(url, 30, 100)
        self.assertEqual(self.server.connections, [])

    def test_follows_relative_redirect_on_the_university(self):
        client = self.client({'/old.pdf': redirect('/new.pdf'), '/new.pdf': ok(b'N')})
        self.assertEqual(client.get(f'{BASE}/old.pdf', 30, 100), b'N')
        self.assertEqual(len(self.server.connections), 1)

    def test_follows_redirect_to_a_university_subdomain(self):
        client = self.client({'/a.pdf': [redirect('https://cms.uni-marburg.de/a.pdf'), ok(b'S')]})
        self.assertEqual(client.get(f'{BASE}/a.pdf', 30, 100), b'S')
        self.assertEqual([c.host for c in self.server.connections], [HOST, 'cms.uni-marburg.de'])

    def test_refuses_redirect_off_the_university_before_following(self):
        for location in ('https://evil.example.org/a.pdf', f'http://{HOST}/a.pdf',
                         '//evil.example.org/a.pdf'):
            client = self.client({'/a.pdf': redirect(location)})
            with self.assertRaisesRegex(ValueError, 'redirected to non-university URL'):
                client.get(f'{BASE}/a.pdf', 30, 100)
            self.assertEqual([c.host for c in self.server.connections], [HOST])

    def test_gives_up_on_redirect_loops(self):
        client = self.client({'/a.pdf': redirect('/a.pdf')})
        with self.assertRaisesRegex(ValueError, 'too many redirects'):
            client.get(f'{BASE}/a.pdf', 30, 100)

    def test_error_status_raises_and_keeps_the_connection(self):
        client = self.client({'/gone.pdf': lambda: FakeResponse(403, b'denied'), '/a.pdf': ok(b'A')})
        with self.assertRaisesRegex(scrape.HTTPStatusError, 'HTTP Error 403: Forbidden'):
            client.get(f'{BASE}/gone.pdf', 30, 100)
        self.assertEqual(client.get(f'{BASE}/a.pdf', 30, 100), b'A')
        self.assertEqual(len(self.server.connections), 1)

    def test_oversized_body_raises_and_drops_the_connection(self):
        client = self.client({'/big.pdf': ok(b'x' * 500), '/a.pdf': ok(b'A')})
        with self.assertRaisesRegex(ValueError, 'larger than 100 bytes'):
            client.get(f'{BASE}/big.pdf', 30, 100)
        self.assertTrue(self.server.connections[0].closed)
        self.assertEqual(client.get(f'{BASE}/a.pdf', 30, 100), b'A')
        self.assertEqual(len(self.server.connections), 2)

    def test_body_of_exactly_the_cap_is_accepted(self):
        client = self.client({'/a.pdf': ok(b'x' * 100)})
        self.assertEqual(len(client.get(f'{BASE}/a.pdf', 30, 100)), 100)

    def test_retries_once_when_the_server_closed_an_idle_connection(self):
        stale = http.client.RemoteDisconnected('closed')
        client = self.client({'/a.pdf': ok(b'A'), '/b.pdf': [stale, ok(b'B')]})
        client.get(f'{BASE}/a.pdf', 30, 100)
        self.assertEqual(client.get(f'{BASE}/b.pdf', 30, 100), b'B')
        self.assertEqual(len(self.server.connections), 2)
        self.assertTrue(self.server.connections[0].closed)

    def test_does_not_retry_on_a_new_connection(self):
        client = self.client({'/a.pdf': [ConnectionResetError('reset'), ok(b'A')]})
        with self.assertRaises(ConnectionResetError):
            client.get(f'{BASE}/a.pdf', 30, 100)
        self.assertEqual(len(self.server.connections), 1)

    def test_does_not_retry_timeouts(self):
        client = self.client({'/a.pdf': ok(b'A'), '/b.pdf': [TimeoutError('timed out'), ok(b'B')]})
        client.get(f'{BASE}/a.pdf', 30, 100)
        with self.assertRaises(TimeoutError):
            client.get(f'{BASE}/b.pdf', 30, 100)
        self.assertTrue(self.server.connections[0].closed)

    def test_close_closes_every_connection(self):
        client = self.client({'/a.pdf': [redirect('https://cms.uni-marburg.de/a.pdf'), ok()]})
        client.get(f'{BASE}/a.pdf', 30, 100)
        client.close()
        self.assertTrue(all(c.closed for c in self.server.connections))


if __name__ == '__main__':
    unittest.main()
