import asyncio
from types import SimpleNamespace

import pytest

from catia_mcp.download import download
from catia_mcp.tools.file_transfer import CHUNK_BYTES, FileTransferTools


class Session:
    def __init__(self, corrupt=False):
        self.corrupt = corrupt

    async def call_tool(self, name, arguments):
        payload = FileTransferTools().execute(name, arguments)
        if self.corrupt and name == "catia_download_file":
            payload["data"]["content_base64"] = "YmFk"
        return SimpleNamespace(structuredContent=payload, isError=not payload["ok"])


@pytest.mark.parametrize("content", [b"", b"abc" * CHUNK_BYTES])
def test_verified_artifact(tmp_path, monkeypatch, content):
    monkeypatch.setenv("CATIA_MCP_TRANSFER_DIR", str(tmp_path))
    source = tmp_path / "source.CATPart"
    source.write_bytes(content)
    output = tmp_path / "artifact.CATPart"
    asyncio.run(download(Session(), str(source), output))
    assert output.read_bytes() == content
    with pytest.raises(FileExistsError):
        asyncio.run(download(Session(), str(source), output))


def test_corrupt_chunk_never_published(tmp_path, monkeypatch):
    monkeypatch.setenv("CATIA_MCP_TRANSFER_DIR", str(tmp_path))
    source = tmp_path / "source.CATPart"
    source.write_bytes(b"original")
    output = tmp_path / "artifact.CATPart"
    with pytest.raises(ValueError, match="checksum"):
        asyncio.run(download(Session(corrupt=True), str(source), output))
    assert not output.exists()
    assert not list(tmp_path.glob(".catia-download-*"))
