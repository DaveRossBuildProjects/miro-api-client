# Miro REST API v2 — endpoint cheat sheet

Base URL: `https://api.miro.com`. All requests use `Authorization: Bearer $MIRO_TOKEN`.
Board IDs in paths must be URL-encoded (`uXjVAbCdEfG=` -> `uXjVAbCdEfG%3D`); the client does this for you.
This sheet is a working summary — when an endpoint returns 400/404 unexpectedly, check https://developers.miro.com/reference for the current shape.

Added in this repo: `POST /v1/boards/{board_id}/copy` copies a board WITH full content (v2 copy_from can create blank boards for rich templates). The copy is named "Copy of ..."; rename with a v2 PATCH. Spaces are created with `POST /v2/orgs/{org_id}/teams/{team_id}/projects` (Enterprise).

## 1. Identity
| Method | Path | Notes |
|---|---|---|
| GET | `/v1/oauth-token` | Token's user, team, scopes. Use to diagnose 401/403. |

## 2. Boards
| Method | Path | Body / params |
|---|---|---|
| GET | `/v2/boards` | `query`, `team_id`, `owner`, `sort`, `limit` (<=50), `offset` |
| GET | `/v2/boards/{board_id}` | — |
| POST | `/v2/boards` | `name`, `description`, `teamId`, `policy` |
| PATCH | `/v2/boards/{board_id}` | `name` (<=60 chars), `description` (<=300), `policy`, `teamId` (move team), `projectId` (move to space/project) |
| PUT | `/v2/boards?copy_from={board_id}` | Copy a board. Body: `name`, `description`, `teamId`, `policy`. May yield a blank board for rich templates; prefer v1 copy. |
| POST | `/v1/boards/{board_id}/copy` | Copy with full content. Named "Copy of ...". |
| DELETE | `/v2/boards/{board_id}` | Moves to trash. Destructive — confirm first. |

`policy` shape:
```json
{
  "permissionsPolicy": {"collaborationToolsStartAccess": "all_editors", "copyAccess": "anyone", "sharingAccess": "team_members_with_editing_rights"},
  "sharingPolicy": {"access": "private", "inviteToAccountAndBoardLinkAccess": "no_access", "organizationAccess": "private", "teamAccess": "private"}
}
```
`access` / `teamAccess` / `organizationAccess` values: `private`, `view`, `comment`, `edit`.
`inviteToAccountAndBoardLinkAccess` takes a role, not an allow/deny flag: `viewer`, `commenter`, `editor`, `coowner`, `owner`, `guest`, `no_access`. It sets what someone gets when they join the account through the board link; it does not control direct email invites.
Verify values against https://developers.miro.com/reference before sending a policy PATCH, and never loosen a policy as a guess to make another call succeed.

## 3. Board members
| Method | Path | Body |
|---|---|---|
| GET | `/v2/boards/{board_id}/members` | offset pagination |
| POST | `/v2/boards/{board_id}/members` | `emails[]`, `role` (`viewer`/`commenter`/`editor`/`coowner`/`owner`), `message`. Returns `successful[]` member IDs and `failed[]` with a reason. |
| GET | `/v2/boards/{board_id}/members/{member_id}` | — |
| PATCH | `/v2/boards/{board_id}/members/{member_id}` | `role` |
| DELETE | `/v2/boards/{board_id}/members/{member_id}` | Destructive. |

## 4. Items (generic)
| Method | Path | Notes |
|---|---|---|
| GET | `/v2/boards/{board_id}/items` | `type` (singular: `sticky_note`, `frame`, `card`, `app_card`, `shape`, `text`, `image`, `document`, `embed`), `parent_item_id`, `limit` (<=50), `cursor` |
| GET | `/v2/boards/{board_id}/items/{item_id}` | — |
| PATCH | `/v2/boards/{board_id}/items/{item_id}` | `position` `{x, y, origin}`, `parent` `{id}` — move items or reparent into a frame |
| DELETE | `/v2/boards/{board_id}/items/{item_id}` | Destructive. |

Positions are relative to the parent frame when an item has a parent; board-absolute otherwise.

## 5. Typed items
Path segment is plural. Each supports POST (create), GET/PATCH/DELETE `/{item_id}`.

| Segment | `data` fields | Common `style` fields |
|---|---|---|
| `sticky_notes` | `content`, `shape` (`square`/`rectangle`) | `fillColor` (named: `yellow`, `light_green`, `red`, `blue`, …), `textAlign` |
| `cards` | `title`, `description`, `dueDate`, `assigneeId` | `cardTheme` (hex) |
| `app_cards` | `title`, `description`, `status` (`connected`/`disconnected`/`disabled`), `fields[]` | `fillColor` |
| `shapes` | `content`, `shape` (`rectangle`, `circle`, `round_rectangle`, …) | `fillColor` (hex), `borderColor`, `fontSize` |
| `texts` | `content` | `color`, `fontSize` |
| `frames` | `title`, `format` (`custom`), `type` (`freeform`) | `fillColor` |
| `images` / `documents` | `url` (or multipart upload) | — |
| `embeds` | `url`, `mode` | — |
| `connectors` | `startItem {id}`, `endItem {id}`, `shape` (`straight`/`elbowed`/`curved`), `captions[]` | `strokeColor`, `endStrokeCap` |

Shared fields on create: `position {x, y}`, `geometry {width, height}`, `parent {id}`.

Example — sticky note inside a frame:
```json
{"data": {"content": "Risk: vendor delay"}, "style": {"fillColor": "red"},
 "position": {"x": 100, "y": 100}, "parent": {"id": "<frame_id>"}}
```

## 6. Tags
| Method | Path | Notes |
|---|---|---|
| GET | `/v2/boards/{board_id}/tags` | — |
| POST | `/v2/boards/{board_id}/tags` | `title` (<=120), `fillColor` (`red`, `light_green`, `cyan`, `yellow`, `magenta`, `green`, `blue`, `gray`, `violet`, `dark_green`, `dark_blue`, `black`) |
| PATCH / DELETE | `/v2/boards/{board_id}/tags/{tag_id}` | — |
| POST | `/v2/boards/{board_id}/items/{item_id}?tag_id={tag_id}` | Attach (sticky notes & cards only; max 8 tags/item) |
| DELETE | `/v2/boards/{board_id}/items/{item_id}?tag_id={tag_id}` | Detach |
| GET | `/v2/boards/{board_id}/items/{item_id}/tags` | Tags on an item |

## 7. Groups & bulk
| Method | Path | Notes |
|---|---|---|
| POST | `/v2/boards/{board_id}/groups` | `data.items[]` item IDs |
| GET/DELETE | `/v2/boards/{board_id}/groups/{group_id}` | DELETE may take `delete_items=true` |
| POST | `/v2/boards/{board_id}/items/bulk` | Array of up to 20 typed item bodies, each with a `type`. Transactional. |

## 8. Enterprise-only (require org admin token / Enterprise plan)
Organization & team management (`/v2/orgs/{org_id}/...`), board export jobs (`/v2/orgs/{org_id}/boards/export/jobs`), audit logs, content classification. Expect 403 with a normal user token.

## 9. Pagination, rate limits, errors
- Cursor pagination (items): response has `cursor`; pass it back until absent.
- Offset pagination (boards, members, tags): `offset` + `limit`, stop at `total`.
- Rate limit is credit-based per user per minute; 429 returns `Retry-After`. The client retries 429/5xx with backoff.
- 401 -> bad/expired token. 403 -> missing scope (`boards:write`, etc.) or no board access. 404 on a real board -> usually an unencoded `=` or the token's user can't see it.
- `INVITATION_FAILED` on share is generic. Common causes, in order: the email is already a member or the owner of the board (check `members list` first); the org restricts sharing outside the company or to approved domains; the token's team can't see the board. Report it and check these; don't change board policy to fix it.
