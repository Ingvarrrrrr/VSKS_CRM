"""SSRF-гейт app.utils.safe_url (аудит безопасности 2026-10-20).

DNS мокается — тест не должен зависеть от реальной сети/резолвера."""
from unittest.mock import patch

import pytest

from app.utils.safe_url import UnsafeUrlError, assert_safe_url


def _fake_getaddrinfo(addrs):
    def _inner(host, *a, **kw):
        return [(None, None, None, None, (a0, 0)) for a0 in addrs]
    return _inner


@pytest.mark.parametrize("addr", ["127.0.0.1", "169.254.169.254", "10.0.0.1", "172.17.0.1", "192.168.1.5"])
def test_rejects_private_and_link_local(addr):
    with patch("socket.getaddrinfo", _fake_getaddrinfo([addr])):
        with pytest.raises(UnsafeUrlError):
            assert_safe_url(f"http://example-internal.test/x")


def test_rejects_bare_hostname_without_dot():
    with pytest.raises(UnsafeUrlError):
        assert_safe_url("http://db/x")
    with pytest.raises(UnsafeUrlError):
        assert_safe_url("http://backend_b/x")


def test_rejects_non_http_scheme():
    with pytest.raises(UnsafeUrlError):
        assert_safe_url("file:///etc/passwd")


def test_rejects_one_bad_address_among_several():
    # DNS rebinding / multi-A-record: ОДИН приватный адрес среди публичных — отказ.
    with patch("socket.getaddrinfo", _fake_getaddrinfo(["93.184.216.34", "127.0.0.1"])):
        with pytest.raises(UnsafeUrlError):
            assert_safe_url("http://example.com/x")


def test_allows_public_address():
    with patch("socket.getaddrinfo", _fake_getaddrinfo(["93.184.216.34"])):
        assert_safe_url("http://example.com/x")  # не должно бросать
