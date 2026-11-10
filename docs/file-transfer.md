# Secure CATIA file transfer (experimental)

The tools `catia_get_file_info` and `catia_download_file` return metadata and
base64 chunks for files that already exist on the CATIA Windows computer.

## Windows configuration

Create a dedicated export directory, e.g. `C:\\CATIA-Exports`. In the
PowerShell terminal that starts the MCP server:

```powershell
$env:CATIA_MCP_TRANSFER_DIR = 'C:\CATIA-Exports'
catia-mcp --http --host 127.0.0.1
```

If remote access is needed, follow `docs/remote-access.md` and use authenticated
HTTPS/private networking. Never expose an unauthenticated CATIA MCP server.

Save or export a CATIA document into the configured directory using the
existing `catia_save_document` or `catia_export` tool. Call
`catia_get_file_info` with the absolute saved file path, then call
`catia_download_file` for each zero-based `chunk_index` with the returned
`sha256`. Base64-decode each chunk, concatenate in order, and verify the
final SHA-256 before offering the file.

Allowed extensions: CATPart, CATProduct, CATDrawing, STEP/STP, STL,
IGES/IGS, 3DXML, PDF, CGR. Files over 256 MiB are rejected. Only files
under the configured directory are accessible; symlink and traversal paths
resolving outside it are rejected.

**Important:** The MCP tools deliver encoded file contents, not an automatic
ChatGPT download attachment. A compatible client-side bridge or host file
integration must reconstruct the binary and attach it. Large files can
exceed MCP message and context limits; for production downloads, prefer a
short-lived authenticated streaming endpoint implemented by a trusted bridge.
Do not paste base64 into the chat transcript.
