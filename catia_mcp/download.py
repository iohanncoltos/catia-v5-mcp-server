"""Reconstruct a verified local artifact using the CATIA MCP tools."""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from catia_mcp.tools.file_transfer import CHUNK_BYTES, MAX_FILE_BYTES


async def download(session, file_path: str, destination: Path) -> Path:
    """Publish only a complete verified file; never overwrite an existing artifact."""
    async def call(name, arguments):
        result = await session.call_tool(name, arguments)
        payload = result.structuredContent
        if payload is None:
            payload = json.loads(next(item.text for item in result.content if item.type == "text"))
        if result.isError or payload.get("ok") is not True:
            raise ValueError(payload.get("message", "Transfer failed"))
        return payload["data"]

    info = await call("catia_get_file_info", {"file_path": file_path})
    size = info["size_bytes"]
    if not isinstance(size, int) or not 0 <= size <= MAX_FILE_BYTES:
        raise ValueError("Invalid transfer size")
    count = max(1, (size + CHUNK_BYTES - 1) // CHUNK_BYTES)
    if info["total_chunks"] != count or info["chunk_size_bytes"] != CHUNK_BYTES:
        raise ValueError("Unsupported chunk layout")
    destination = Path(destination).absolute()
    if destination.exists():
        raise FileExistsError(destination)
    digest = hashlib.sha256()
    descriptor, temporary = tempfile.mkstemp(dir=destination.parent, prefix=".catia-download-")
    try:
        with os.fdopen(descriptor, "wb") as stream:
            for index in range(count):
                chunk = await call("catia_download_file", {
                    "file_path": file_path, "expected_sha256": info["sha256"],
                    "chunk_index": index,
                })
                if any(chunk[key] != info[key] for key in (
                    "sha256", "size_bytes", "total_chunks", "chunk_size_bytes", "file_name"
                )) or chunk["chunk_index"] != index:
                    raise ValueError("Inconsistent chunk metadata")
                raw = base64.b64decode(chunk["content_base64"], validate=True)
                expected_length = min(CHUNK_BYTES, size - index * CHUNK_BYTES)
                if len(raw) != expected_length or hashlib.sha256(raw).hexdigest() != chunk["chunk_sha256"]:
                    raise ValueError("Invalid chunk size or checksum")
                stream.write(raw)
                digest.update(raw)
            if digest.hexdigest() != info["sha256"]:
                raise ValueError("Final file checksum mismatch")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
    finally:
        os.unlink(temporary)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Existing authenticated MCP HTTP endpoint")
    parser.add_argument("--file", required=True, help="Absolute path on the CATIA computer")
    parser.add_argument("--output", required=True, type=Path, help="New local artifact path")
    arguments = parser.parse_args()

    async def run():
        token = os.environ.get("CATIA_MCP_DOWNLOAD_TOKEN")
        headers = {"Authorization": f"Bearer {token}"} if token else None
        async with streamablehttp_client(arguments.url, headers=headers) as (reader, writer, _):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                path = await download(session, arguments.file, arguments.output)
                print(f"Verified local file: {path}")
                print("The host must publish this file as an attachment; MCP does not attach it.")

    asyncio.run(run())


if __name__ == "__main__":
    main()
