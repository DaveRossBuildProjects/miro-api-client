# Miro API Client

A thin, dependency-free (stdlib only) Python client and CLI for the Miro REST API v2, built so Claude (Claude Code or Cowork) can do the things the Miro MCP connector cannot.

## The problem

The Miro MCP connector is great for reading boards and creating diagrams, tables and docs, but it has no tools for many template and admin tasks: copying or deleting boards, sharing and changing member roles, moving boards between teams or spaces, changing sharing policy, tags, precise item moves and reparenting into frames, bulk edits, app cards, connectors, and Enterprise admin endpoints. Without a bridge, those jobs mean manual clicking or one-off scripts with pasted tokens.

## The solution

`miro_api.py` wraps the REST API with safe defaults and gives Claude two ways in:

- **CLI**: `python miro_api.py <group> <command>`, JSON out, errors as JSON on stderr.
- **Python import**: `from miro_api import MiroClient` for multi-step and bulk work.

It is packaged as a Claude skill ([docs/claude-skill-SKILL.md](docs/claude-skill-SKILL.md)) with an MCP-first routing rule: use the connector when it can do the job, REST for the gaps.

Features: automatic board-ID URL-encoding and URL parsing, token discovery that never prints the token, retry with backoff on 429/5xx, cursor and offset pagination, `--dry-run` on every command, `--yes` required for deletes and removals, and a `request` escape hatch for any endpoint (including `/v1` and Enterprise `/v2/orgs/...`).

## Quick start

```bash
mkdir -p ~/.miro && (umask 077; read -rs T && printf '%s' "$T" > ~/.miro/token)   # paste token, hidden
python miro_api.py whoami
python miro_api.py board get https://miro.com/app/board/<id>/
python miro_api.py board copy-v1 <template> --name "Workshop - Acme"
python miro_api.py members share <board> a@acme.com --role editor
python miro_api.py board update <board> --project-id <space_id>
python miro_api.py --dry-run board delete <board> --yes
```

Setup, including how to create the Miro app and use it from Claude Code, is in [docs/implementation-guide.md](docs/implementation-guide.md). Diagrams are in [docs/architecture.md](docs/architecture.md). Endpoint cheat sheet: [references/endpoints.md](references/endpoints.md).

## Command groups

| Group | Commands |
|---|---|
| `whoami` | token owner, team, scopes, token source |
| `board` | list, get, create, update, rename, copy, **copy-v1**, delete |
| `members` | list, share, update, remove |
| `items` | list, get, create, update, delete |
| `tags` | list, create, attach, detach, delete |
| `request` | any method and path, `{board}` placeholder, `--param`, `--data` |

## Known caveat

`board copy` uses v2 `copy_from`, which for rich templates (dot voting, polls, prototyping screens, QR companions and similar) can return success but create a blank board. Use `board copy-v1` for content-faithful copies. Check the new board's item count against the template.

## Related

[miro-board-provisioner](https://github.com/DaveRossBuildProjects/miro-board-provisioner) uses the same API techniques to provision 160+ workshop boards from a CSV.

## License

MIT. See [LICENSE](LICENSE).
