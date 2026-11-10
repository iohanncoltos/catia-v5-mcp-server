"""Remote (Streamable HTTP) transport: auth gate, bind policy, end-to-end MCP."""

import asyncio
import socket

import httpx
import pytest
import uvicorn
from mcp import ClientSession

try:  # mcp >= 1.28 renamed the client and takes an httpx client
    from mcp.client.streamable_http import streamable_http_client

    def open_client(url, headers):
        return streamable_http_client(url, http_client=httpx.AsyncClient(headers=headers))

except ImportError:  # pragma: no cover - older SDKs
    from mcp.client.streamable_http import streamablehttp_client

    def open_client(url, headers):
        return streamablehttp_client(url, headers=headers)

from catia_mcp.http_transport import build_app, check_bind, is_loopback
from catia_mcp.server import CATIAMCPServer, parse_args
from catia_mcp.download import download

TOKEN = "test-token-0123456789abcdef"


def test_download_over_authenticated_http(tmp_path, monkeypatch):
    source = tmp_path / "source.CATPart"
    source.write_bytes(b"CAD binary\x00" * 20000)
    monkeypatch.setenv("CATIA_MCP_TRANSFER_DIR", str(tmp_path))
    output = tmp_path / "download.CATPart"

    async def body(url, _):
        from mcp.client.streamable_http import streamablehttp_client
        async with streamablehttp_client(url, headers={
            "Authorization": f"Bearer {TOKEN}"
        }) as (reader, writer, _):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                await download(session, str(source), output)

    asyncio.run(_with_server(TOKEN, body))
    assert output.read_bytes() == source.read_bytes()


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.parametrize(
    ("host", "expected"),
    [("127.0.0.1", True), ("localhost", True), ("::1", True), ("0.0.0.0", False), ("10.0.0.5", False)],
)
def test_is_loopback(host, expected):
    assert is_loopback(host) is expected


def test_non_loopback_bind_requires_token():
    with pytest.raises(SystemExit, match="without a token"):
        check_bind("0.0.0.0", None)
    with pytest.raises(SystemExit, match="16 characters"):
        check_bind("0.0.0.0", "short")
    check_bind("0.0.0.0", TOKEN)
    check_bind("127.0.0.1", None)


def test_cli_defaults_keep_stdio():
    args = parse_args([])
    assert args.http is False and args.host == "127.0.0.1" and args.port == 8765


async def _with_server(token, body):
    mcp_server = CATIAMCPServer()
    port = free_port()
    app = build_app(mcp_server.server, "127.0.0.1", port, token)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    task = asyncio.create_task(server.serve())
    try:
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(0.05)
        await body(f"http://127.0.0.1:{port}/mcp", mcp_server)
    finally:
        server.should_exit = True
        await task
        await mcp_server.close()


def test_missing_or_wrong_token_is_rejected():
    async def body(url, _):
        async with httpx.AsyncClient() as client:
            for headers in ({}, {"Authorization": "Bearer wrong-token-0123456789"}):
                response = await client.post(url, json={}, headers=headers)
                assert response.status_code == 401
            other = await client.get(url.replace("/mcp", "/other"))
            assert other.status_code == 404

    asyncio.run(_with_server(TOKEN, body))


def test_authenticated_client_lists_tools_and_gets_structured_errors(monkeypatch):
    async def body(url, mcp_server):
        def boom():
            raise RuntimeError("No active document")

        monkeypatch.setattr(mcp_server.connection, "ensure_connected", boom)
        headers = {"Authorization": f"Bearer {TOKEN}"}
        async with (
            open_client(url, headers) as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            tools = await session.list_tools()
            assert len(tools.tools) == 100
            result = await session.call_tool("catia_list_documents", {})
            assert result.isError is True
            assert result.structuredContent["code"] == "COM_ERROR"
            # The server keeps serving after an ordinary error.
            again = await session.call_tool("catia_list_documents", {})
            assert again.isError is True

    asyncio.run(_with_server(TOKEN, body))


def test_loopback_without_token_rejects_foreign_host_header():
    async def body(url, _):
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
                headers={"Host": "evil.example", "Accept": "application/json, text/event-stream"},
            )
            assert response.status_code in (400, 403, 421)

    asyncio.run(_with_server(None, body))
