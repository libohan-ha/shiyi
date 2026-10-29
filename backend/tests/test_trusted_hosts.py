from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.hosts import TrustedHosts, host_name, parse_hosts


def make_client(hosts):
    app = FastAPI()
    app.add_middleware(TrustedHosts, allowed_hosts=parse_hosts(hosts))

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    return TestClient(app)


def status(client, host):
    return client.get("/api/health", headers={"host": host}).status_code


def test_default_app_still_rejects_unknown_hosts(client):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/health", headers={"host": "127.0.0.1:8765"}).status_code == 200
    response = client.get("/api/health", headers={"host": "my-pc.tail1234.ts.net:8765"})
    assert response.status_code == 400
    assert response.text == "Invalid host header"


def test_configured_tailnet_hosts_are_accepted():
    client = make_client("localhost,127.0.0.1,100.101.102.103,My-PC,my-pc.tail1234.ts.net,fd7a:115c:a1e0::1")
    for host in ("127.0.0.1:8765", "localhost:8765", "100.101.102.103:8765", "my-pc:8765",
                 "MY-PC:8765", "My-PC.Tail1234.ts.net:8765", "[fd7a:115c:a1e0::1]:8765"):
        assert status(client, host) == 200, host


def test_unconfigured_hosts_are_still_rejected():
    client = make_client("localhost,127.0.0.1,100.101.102.103")
    for host in ("100.101.102.104:8765", "other-pc:8765", "evil.example", "", "[fd7a::2]:8765"):
        assert status(client, host) == 400, host


def test_wildcard_suffix():
    client = make_client("localhost,*.tail1234.ts.net")
    assert status(client, "my-pc.tail1234.ts.net") == 200
    assert status(client, "tail1234.ts.net.evil.example") == 400


def test_parsing_helpers():
    assert parse_hosts(" LocalHost , ,[FD7A::1],localhost") == ["localhost", "fd7a::1"]
    assert host_name("[::1]:8765") == "::1"
    assert host_name("Example.COM:80") == "example.com"
