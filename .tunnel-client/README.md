# Signal over Secure MCP Tunnel

Run the Signal MCP server on the Mac that has Signal Desktop and the linked
signal-cli account. The outbound tunnel gives authorized ChatGPT callers access
to the server's tools, including message reads and sends. Signal's local account
data stays on the Mac. Tool results are returned to the caller.

1. Complete the repository's [local setup](../README.md), including linking
   signal-cli for sends. Run `uv run --frozen signal-mcp smoke` from the root
   to check that the server can initialize.
2. Install the OpenAI tunnel client and 1Password CLI. Create a separate Signal
   tunnel in OpenAI Platform settings and save a runtime key with Tunnels Read
   and Use permissions from that organization in 1Password.
3. Copy `.tunnel-client/.env.example` to `.tunnel-client/.env.local`, run
   `chmod 600 .tunnel-client/.env.local`, and fill in the tunnel ID, organization
   ID, and quoted `op://` secret reference. Use only trusted shell assignments
   in this file. Keep Signal settings in the repository root's `.env.local`.
4. Run `.tunnel-client/start.sh`. It runs the client doctor before starting
   the tunnel. Leave it running in the foreground and stop it with Ctrl-C.
5. Check `http://127.0.0.1:8081/healthz` and
   `http://127.0.0.1:8081/readyz`. Port 8081 leaves port 8080 available for
   iMessage. If needed, set `HEALTH_LISTEN_ADDR` to another loopback address
   and port in the tunnel environment file.
6. Associate the tunnel with the intended ChatGPT workspace, add the connector,
   and verify tool discovery. Call `list_chats` with `limit=1` to verify a
   read end to end. Restart the launcher and repeat the read to check recovery.

`local-stdio.yaml` sets `poll_channels: [main]`, so the client ignores other control-plane channels (for example `harpoon`) instead of logging `unsupported channel` errors.
