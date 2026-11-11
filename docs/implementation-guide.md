# Implementation Guide

## 1. Create a Miro app so Claude can act on templates and admin settings

The client authenticates as you through a Miro app that you create and install on a team. Think of the app as a named, scoped, revocable credential.

1. Go to **Profile settings, Your apps** (https://miro.com/app/settings/user-profile/apps) and choose **Create new app**.
2. Name it clearly (for example "Claude gateway to Miro API v2") and choose the team it will act in. A token is bound to the team it is installed on.
3. Under **Permissions**, grant the minimum you need:
   - `boards:read` and `boards:write` for boards, items, tags and sharing
   - `projects:read` and `projects:write` for spaces
   - `team:read` and `identity:read` if you want fuller `whoami` output
   - Enterprise admin endpoints (`/v2/orgs/...`) need additional org-level scopes and an org admin's approval
4. OAuth-only fields can hold placeholders for a personal token app: App URL `https://localhost`, Redirect URI `https://localhost/callback`.
5. Select **Install app and get OAuth token**, pick the team, and copy the access token.
6. If your org requires admin approval for new apps, the install stays pending until an admin approves it. There is no workaround; ask an admin to approve, or to create the app and token themselves.

### Using several apps

Different jobs can use different apps (for example one app for board duplication, one general gateway) so each can be scoped narrowly and revoked independently. Point the client at the one you want with `MIRO_TOKEN` or `MIRO_TOKEN_FILE`.

### Token hygiene

- The **client secret** is only for OAuth code flows and is not used by this client. Do not store it anywhere in a project.
- Never paste a token into a chat, issue, or commit. Create the token file yourself so the value never lands in a transcript.
- If a token or secret is exposed: revoke the app's client secret, regenerate the OAuth token, reinstall if needed, and update wherever it is stored.
- Prefer apps whose access tokens can expire and be refreshed when your org policy allows it.

## 2. Install the client

It is a single file with no dependencies (Python 3.8+).

```bash
git clone <this repo> && cd miro-api-client
python miro_api.py --help
```

## 3. Provide the token

The client looks, in order, at: the `MIRO_TOKEN` environment variable, a path in `MIRO_TOKEN_FILE`, `./.miro_token`, then `~/.miro/token`. The file holds only the token on one line. It never prints the token; `whoami` reports only where it found one.

```bash
mkdir -p ~/.miro && chmod 700 ~/.miro
( umask 077; read -rs T && printf '%s' "$T" > ~/.miro/token )
python miro_api.py whoami
```

`whoami` shows the token's user, team and scopes, which is the fastest way to explain a 401 (bad or expired token) or 403 (missing scope or no board access).

## 4. Use it with Claude Code

1. Copy the skill into your Claude Code skills folder so Claude finds it by intent:

   ```bash
   mkdir -p ~/.claude/skills/miro-rest-api/{scripts,references}
   cp miro_api.py ~/.claude/skills/miro-rest-api/scripts/
   cp references/endpoints.md ~/.claude/skills/miro-rest-api/references/
   cp docs/claude-skill-SKILL.md ~/.claude/skills/miro-rest-api/SKILL.md
   ```

2. Keep the Miro MCP connector enabled. The skill's rule is MCP first, REST for gaps.
3. Ask Claude in plain language, for example "copy the PI Planning template for Acme, move it into the Acme space and share it with these three people". Claude runs `--dry-run` first for destructive or bulk work and asks you to confirm.
4. Claude Code runs on your machine and has no network allowlist. In Claude Cowork's sandbox, `api.miro.com` may be blocked ("Tunnel connection failed: 403"); an org owner must allow the domain, or run the client locally.

## 5. Common recipes

```bash
# Duplicate a rich template with content, rename it, move it into a space, share it
python miro_api.py board copy-v1 <template> --name "Acme PI Planning"
python miro_api.py board update <new_board> --project-id <space_id>
python miro_api.py members share <new_board> pm@acme.com --role editor --message "Your board"

# Inspect or change sharing policy (verify values in the Miro reference first)
python miro_api.py board get <board>
python miro_api.py board update <board> --policy '{"sharingPolicy":{"access":"view"}}'

# Move a board to another team
python miro_api.py board update <board> --team-id <team_id>

# Any other endpoint, including Enterprise
python miro_api.py request GET "/v2/boards/{board}/items" --board <board> --param type=frame
python miro_api.py request POST "/v2/orgs/<org_id>/teams/<team_id>/projects" --data '{"name":"Acme"}'

# Bulk work from Python
python - <<'PY'
from miro_api import MiroClient
c = MiroClient()
tag = c.create_tag("<board>", "Needs review", "yellow")
for it in c.list_items("<board>", item_type="sticky_note"):
    if "risk" in it["data"].get("content", "").lower():
        c.attach_tag("<board>", it["id"], tag["id"])
PY
```

## 6. Safety model

- Deletes and member removals require `--yes`; otherwise the client refuses.
- Run `--dry-run` before any destructive or bulk write (delete, remove member, policy change, more than about 10 item edits) and confirm the plan.
- Sharing to external emails exposes board content outside your org; confirm first.
- Do not loosen a board policy as a guess to make another call succeed.
- Tokens are never echoed. `whoami` shows the token source, not its value.

## 7. Troubleshooting

| Symptom | Likely cause |
|---|---|
| 401 | Bad or expired token. Regenerate and replace. |
| 403 | Missing scope, no access to the board, or an Enterprise endpoint called with a non-admin token. |
| 404 on a real board | Unencoded `=` in a path (the client encodes it), or the token's user cannot see the board. |
| 404 on a new-looking endpoint | The endpoint is not public. Check the Miro reference; spaces use the org-scoped endpoint. |
| Blank board after `board copy` | v2 `copy_from` limitation on rich templates. Use `board copy-v1`. |
| `INVITATION_FAILED` on share | Already a member or owner, org restricts external or unapproved domains, or the token's team cannot see the board. |
| "Tunnel connection failed: 403" | The runtime blocks `api.miro.com`. Allow the domain or run locally. |
| 429 | Handled automatically with backoff; slow bulk loops if it persists. |
