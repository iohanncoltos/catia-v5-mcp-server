"""File transfer tests run without CATIA or Windows COM."""
import base64
import hashlib

from catia_mcp.tools.file_transfer import CHUNK_BYTES, FileTransferTools


def test_transfer_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("CATIA_MCP_TRANSFER_DIR", str(tmp_path))
    content = b"A" * (CHUNK_BYTES + 17)
    path = tmp_path / "sample.CATPart"
    path.write_bytes(content)
    tools = FileTransferTools()
    info = tools.execute("catia_get_file_info", {"file_path": str(path)})
    assert info["ok"]
    data = info["data"]
    assert data["total_chunks"] == 2
    chunks = []
    for i in range(2):
        response = tools.execute("catia_download_file", {
            "file_path": str(path), "expected_sha256": data["sha256"], "chunk_index": i
        })
        assert response["ok"]
        chunk = base64.b64decode(response["data"]["content_base64"])
        assert hashlib.sha256(chunk).hexdigest() == response["data"]["chunk_sha256"]
        chunks.append(chunk)
    assert b"".join(chunks) == content


def test_reject_outside_root(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    other = tmp_path / "secret.CATPart"
    other.write_bytes(b"secret")
    monkeypatch.setenv("CATIA_MCP_TRANSFER_DIR", str(allowed))
    result = FileTransferTools().execute("catia_get_file_info", {"file_path": str(other)})
    assert not result["ok"]


def test_reject_unsupported_extension(tmp_path, monkeypatch):
    monkeypatch.setenv("CATIA_MCP_TRANSFER_DIR", str(tmp_path))
    path = tmp_path / "private.txt"
    path.write_text("private")
    result = FileTransferTools().execute("catia_get_file_info", {"file_path": str(path)})
    assert not result["ok"]


def test_reject_stale_hash(tmp_path, monkeypatch):
    monkeypatch.setenv("CATIA_MCP_TRANSFER_DIR", str(tmp_path))
    path = tmp_path / "sample.stp"
    path.write_bytes(b"hello")
    result = FileTransferTools().execute("catia_download_file", {
        "file_path": str(path), "expected_sha256": "0" * 64,
    })
    assert not result["ok"]
