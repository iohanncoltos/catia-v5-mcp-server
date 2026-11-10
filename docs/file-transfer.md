# Secure CATIA file transfer (experimental)

## Download bridge and ChatGPT limitations

`catia-mcp-download` is a real MCP HTTP client that writes a binary artifact on
the client computer. It checks every chunk, the total size and the final SHA-256,
cleans up failed downloads, and refuses to replace an existing destination.
The destination directory must already exist. File names returned by the server
are never used as destination paths.

```powershell
python -m pip install -e .
$env:CATIA_MCP_DOWNLOAD_TOKEN = '<existing server bearer token>'
python -m catia_mcp.download --url http://127.0.0.1:8000/mcp --file C:\CATIA-Exports\part.CATPart --output C:\ChatArtifacts\part.CATPart
```

Use the actual URL/port printed by your server. For remote connections use the
authenticated HTTPS endpoint; the bridge does not create a public file server.
Set the token in the bridge process environment, never in chat or command arguments.

In a desktop Work/Codex session with filesystem access, the agent can run this
bridge into its session's outputs directory and provide the resulting local file
through the host's file delivery UI. This is a local artifact link, not proof that
the file was uploaded to a cloud ChatGPT conversation. If the host cannot run the
bridge or publish local files, manual upload or a separate supported integration
is still necessary. Binary CAD previews/analysis are client dependent.

The official plugin reference documents optional widget file helpers, but does
not establish that arbitrary base64 MCP tool results become attachments:
https://developers.openai.com/plugins/reference#file-apis
The `openaiFileResponse` mechanism belongs to GPT Actions, a different transport:
https://developers.openai.com/api/docs/actions/sending-files
Adding that property to an MCP result does not establish compatibility. No
automatic cloud attachment support is claimed or tested by this implementation.

After pulling/merging this change, reinstall with `python -m pip install -e .`
in the server's Python environment. Set `CATIA_MCP_TRANSFER_DIR` in the environment
of the actual server process (a service needs service configuration, not just a
new terminal variable). Restart that MCP process, then refresh/reconnect the
ChatGPT connector so cached tool definitions and server instructions refresh.
CATIA itself does not need restarting for file transfer. Existing running
servers do not load changed Python code automatically.

Keep `Racord_Curbat_Flanse_69_WIP.CATPart` explicitly marked as incomplete.
To transfer it, copy it into the dedicated transfer directory without renaming
it as final. Successful transfer verifies bytes, not drawing compliance.

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

Each call reads a bounded in-memory snapshot so the returned hash and chunk
refer to the same bytes. Budget up to 256 MiB of memory per call. The transfer
directory and its parent directories must be writable only by trusted local
users; this is not a sandbox against local users replacing files or links.
