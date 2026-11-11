---
name: "miro-rest-api"
description: Execute Miro actions through the Miro REST API v2 when the Miro MCP connector can't do them — sharing a board or changing member roles, copying/duplicating a board, deleting boards or items, moving a board to another team or space, changing sharing policy, creating/attaching tags, precise item moves or reparenting into frames, bulk edits across many items, app cards, connectors, or any raw API endpoint. Use this skill whenever a Miro request fails or has no matching MCP tool, when the user mentions the Miro API, REST, endpoints, or a Miro access token, or asks to do something to a Miro board "via the API", even if they don't name this skill.
---

# Miro REST API

A thin Python client (`scripts/miro_api.py`, stdlib only) plus CLI for Miro's REST API v2. It fills gaps in the Miro MCP connector; it doesn't replace it.

## Routing: MCP first, REST for gaps

Check for a Miro MCP tool before reaching for REST. MCP tools are authenticated already, render nice previews, and are what the user expects by default. For example, board renames and description changes are covered by `board_update_metadata`; diagrams, tables, docs, and reading board content are covered by the canvas/table/board tools.

Use this skill when:
- No MCP tool exists for the action (sharing, copy, delete, tags, sharing policy, moving a board between teams, connectors, app cards, bulk ops).
- An MCP tool returned an error or can't express what's needed (e.g., exact coordinates, reparenting an item into a frame).
- The user explicitly asks for the API.

Mixing is fine: read with MCP, write with REST, then use MCP `board_show` to preview the result.

## Setup check (do this first, once per session)

1. **Token**: the client looks, in order, at the `MIRO_TOKEN` env var, a path in `MIRO_TOKEN_FILE`, `.miro_token` in the current working folder, then `~/.miro/token`. The file holds just the token on one line.
   - Claude Code: `export MIRO_TOKEN=...` in the shell profile, or `~/.miro/token`.
   - Cowork: there's no shell profile, so the user puts `.miro_token` in the folder they've connected to Cowork and runs commands from that folder (or sets `MIRO_TOKEN_FILE`).
   - If no token is found, walk the user through getting one: Miro → Settings → Your apps → Create new app → scopes `boards:read`, `boards:write` (add `team:read`, `identity:read` if needed) → Install app and get OAuth token.
   - Never read the token file aloud, echo it, paste it into chat, or copy it anywhere else. Don't create the token file yourself from a token the user pastes into chat; ask them to create it so the value doesn't end up in the transcript. Remind them to keep `.miro_token` out of shared or synced folders and to `chmod 600` it.
2. **Network**: run `python scripts/miro_api.py whoami`. If it fails with "Host not in allowlist" or another network error, `api.miro.com` isn't reachable from this environment and an org owner must add it to the allowed domains (claude.ai sandbox, and possibly Cowork's VM). Claude Code on the user's machine has no such allowlist. Tell the user which case applies rather than retrying.
3. `whoami` also shows the token's user, team, scopes, and `token_source` (where the token was found, never the value) — use it to explain 401/403s.

## Usage

Run from the skill directory (or reference the script by full path). Board arguments accept a full board URL or a raw ID; encoding of `=` is handled.

```bash
S=scripts/miro_api.py
python $S whoami
python $S board get  https://miro.com/app/board/uXjVAbCdEfG=/
python $S board update <board> --name "Q3 PI Planning" --description "ART Alpha"
python $S board copy <board> --name "PI Planning — Acme" [--team-id 3458...]
python $S board copy-v1 <board> --name "PI Planning — Acme"   # full-content copy for rich templates
python $S board update <board> --project-id <space_id>        # move into a space
python $S board update <board> --policy '{"sharingPolicy":{"access":"view"}}'
python $S members list  <board>
python $S members share <board> a@acme.com b@acme.com --role editor --message "Workshop board"
python $S items list <board> --type sticky_note --all
python $S items list <board> --parent <frame_id> --all
python $S items create <board> sticky_notes --data '{"data":{"content":"Hi"},"position":{"x":0,"y":0}}'
python $S items update <board> <item_id> --data '{"parent":{"id":"<frame_id>"},"position":{"x":50,"y":50}}'
python $S items update <board> <item_id> --type sticky_notes --data '{"style":{"fillColor":"red"}}'
python $S tags create <board> "Blocked" --color red
python $S tags attach <board> <item_id> <tag_id>
python $S request GET "/v2/boards/{board}/items/<id>/tags" --board <board>   # any endpoint
```

Output is JSON on stdout; errors are JSON on stderr with status and response body. Read the body before retrying — Miro's error messages usually name the bad field.

For endpoint shapes, field names, color values, and pagination details, read `references/endpoints.md`. For anything not listed there, use the `request` subcommand and check https://developers.miro.com/reference.

For multi-step or bulk work, import the client instead of looping the CLI:

```python
import sys; sys.path.insert(0, "scripts")
from miro_api import MiroClient
c = MiroClient()
tag = c.create_tag(board, "Needs review", "yellow")
for item in c.list_items(board, item_type="sticky_note"):
    if "risk" in item["data"].get("content", "").lower():
        c.attach_tag(board, item["id"], tag["id"])
```

## Safety

Deletes and member removals require `--yes`; the CLI refuses otherwise. Before any destructive or bulk write (delete, remove member, change sharing policy, edits to more than ~10 items), run the same command with `--dry-run` first, show the user what will happen in a sentence or two, and get explicit confirmation. Sharing a board with external emails also deserves a quick confirm, since it exposes content outside the org.

When done, confirm briefly what changed. If the MCP `board_show` tool is available, use it to preview the board instead of describing it.
