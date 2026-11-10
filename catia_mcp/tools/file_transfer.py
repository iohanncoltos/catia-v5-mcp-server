"""Restricted, chunked read-only downloads of CATIA output files.

Set CATIA_MCP_TRANSFER_DIR to an explicit directory before enabling these tools.
File contents are returned as base64 in small chunks; the MCP client must
assemble them to offer an actual downloadable attachment.
"""
from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
from typing import Any

from catia_mcp.results import operation_result

ALLOWED_SUFFIXES = {
    ".catpart", ".catproduct", ".catdrawing", ".stp", ".step",
    ".stl", ".igs", ".iges", ".3dxml", ".pdf", ".cgr",
}
CHUNK_BYTES = 128 * 1024
MAX_FILE_BYTES = 256 * 1024 * 1024


class FileTransferTools:
    def get_tool_definitions(self) -> list[dict[str, Any]]:
        path = {"type": "string", "description": "Absolute path within CATIA_MCP_TRANSFER_DIR"}
        return [
            {
                "name": "catia_get_file_info",
                "description": "Inspect a CATIA output file in the configured transfer directory.",
                "inputSchema": {
                    "type": "object", "properties": {"file_path": path},
                    "required": ["file_path"], "additionalProperties": False,
                },
            },
            {
                "name": "catia_download_file",
                "description": (
                    "Read one base64-encoded chunk of a CATIA file from the restricted "
                    "transfer directory. Reassemble chunks on the client; this tool "
                    "does not itself attach a file to ChatGPT."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": path,
                        "chunk_index": {"type": "integer", "minimum": 0, "default": 0},
                        "expected_sha256": {
                            "type": "string", "pattern": "^[a-fA-F0-9]{64}$",
                            "description": "SHA-256 from catia_get_file_info; prevents changed-file reads",
                        },
                    },
                    "required": ["file_path", "expected_sha256"],
                    "additionalProperties": False,
                },
            },
        ]

    @staticmethod
    def _file(file_path: str) -> Path:
        root_value = os.environ.get("CATIA_MCP_TRANSFER_DIR", "").strip()
        if not root_value:
            raise ValueError("CATIA_MCP_TRANSFER_DIR is not configured")
        root = Path(root_value).resolve(strict=True)
        if not root.is_dir():
            raise ValueError("Transfer root must be a directory")
        candidate = Path(file_path)
        if not candidate.is_absolute():
            raise ValueError("An absolute file path is required")
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise ValueError("File is outside CATIA_MCP_TRANSFER_DIR")
        if not resolved.is_file() or resolved.suffix.lower() not in ALLOWED_SUFFIXES:
            raise ValueError("Unsupported file or file type")
        if resolved.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("File exceeds the 256 MiB transfer limit")
        return resolved

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            path = self._file(arguments["file_path"])
            size = path.stat().st_size
            sha = self._sha256(path)
            common = {
                "file_name": path.name, "size_bytes": size, "sha256": sha,
                "chunk_size_bytes": CHUNK_BYTES,
                "total_chunks": max(1, (size + CHUNK_BYTES - 1) // CHUNK_BYTES),
            }
            if tool_name == "catia_get_file_info":
                data = common
            elif tool_name == "catia_download_file":
                if sha != arguments["expected_sha256"].lower():
                    raise ValueError("File changed since metadata was retrieved")
                index = arguments.get("chunk_index", 0)
                if index < 0 or index >= common["total_chunks"]:
                    raise ValueError("chunk_index out of range")
                with path.open("rb") as stream:
                    stream.seek(index * CHUNK_BYTES)
                    raw = stream.read(CHUNK_BYTES)
                if self._sha256(path) != sha:
                    raise ValueError("File changed during transfer")
                data = {
                    **common, "chunk_index": index,
                    "content_base64": base64.b64encode(raw).decode("ascii"),
                    "chunk_sha256": hashlib.sha256(raw).hexdigest(),
                }
            else:
                raise ValueError("Unknown file transfer tool")
            return operation_result(
                tool=tool_name, ok=True, code="OK",
                message="File metadata ready" if tool_name == "catia_get_file_info" else "Chunk ready",
                data=data, modified=False,
            )
        except (OSError, ValueError) as error:
            return operation_result(
                tool=tool_name, ok=False, code="FILE_TRANSFER_ERROR",
                message=str(error), data={}, modified=False,
            )
