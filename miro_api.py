#!/usr/bin/env python3
"""
miro_api.py - thin, dependency-free client + CLI for the Miro REST API v2.

Use it for actions the Miro MCP connector doesn't expose (sharing, copying,
deleting, tags, precise item moves, bulk edits, arbitrary endpoints).

Auth:   export MIRO_TOKEN=<token>, or put the token in ./.miro_token or ~/.miro/token
Docs:   https://developers.miro.com/reference

Examples:
  python miro_api.py whoami
  python miro_api.py board get https://miro.com/app/board/uXjVAbCdEfG=/
  python miro_api.py board update <board> --name "New name" --description "..."
  python miro_api.py board copy <board> --name "Copy for Acme"
  python miro_api.py members share <board> a@x.com b@y.com --role editor
  python miro_api.py items list <board> --type sticky_note --all
  python miro_api.py tags attach <board> <item_id> <tag_id>
  python miro_api.py request GET /v2/boards/{board}/items --param type=frame
  python miro_api.py --dry-run board delete <board> --yes

Every command prints JSON to stdout. Errors print JSON to stderr, exit 1.
Importable too:  from miro_api import MiroClient
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = os.environ.get("MIRO_API_BASE", "https://api.miro.com")
MAX_RETRIES = 5


class MiroError(Exception):
    def __init__(self, status, body, method, url):
        self.status, self.body, self.method, self.url = status, body, method, url
        super().__init__(f"{method} {url} -> HTTP {status}: {body}")


def board_id_from(ref: str) -> str:
    """Accept a board URL or raw ID; return the raw (unencoded) board ID."""
    m = re.search(r"/board/([^/?#]+)", ref)
    return urllib.parse.unquote(m.group(1) if m else ref.strip())


def enc(board_ref: str) -> str:
    """URL-encode a board ID for use in a path (IDs often end in '=')."""
    return urllib.parse.quote(board_id_from(board_ref), safe="")


TOKEN_FILE_CANDIDATES = [".miro_token", os.path.join("~", ".miro", "token")]


def resolve_token():
    """Find a token without ever printing it. Order:
    1. MIRO_TOKEN env var
    2. MIRO_TOKEN_FILE env var (path to a file)
    3. ./.miro_token in the current working folder (handy for Cowork)
    4. ~/.miro/token
    Returns (token, source) or (None, None)."""
    if os.environ.get("MIRO_TOKEN", "").strip():
        return os.environ["MIRO_TOKEN"].strip(), "env:MIRO_TOKEN"
    paths = []
    if os.environ.get("MIRO_TOKEN_FILE"):
        paths.append(os.environ["MIRO_TOKEN_FILE"])
    paths += TOKEN_FILE_CANDIDATES
    for p in paths:
        full = os.path.abspath(os.path.expanduser(p))
        if os.path.isfile(full):
            with open(full) as f:
                tok = f.read().strip()
            if tok:
                _warn_if_open_perms(full)
                return tok, f"file:{full}"
    return None, None


def _warn_if_open_perms(path):
    if os.name != "posix":
        return
    try:
        if os.stat(path).st_mode & 0o077:
            print(f"warning: {path} is readable by other users; run: chmod 600 {path}", file=sys.stderr)
    except OSError:
        pass


class MiroClient:
    def __init__(self, token=None, dry_run=False, base_url=BASE_URL):
        if token:
            self.token, self.token_source = token, "argument"
        else:
            self.token, self.token_source = resolve_token()
        self.dry_run = dry_run
        self.base_url = base_url.rstrip("/")
        if not self.token and not dry_run:
            raise SystemExit(
                "No Miro token found. Create an app at "
                "https://miro.com/app/settings/user-profile/apps, install it to your team, "
                "then either export MIRO_TOKEN=..., or save the token (just the token, one line) "
                "to .miro_token in your working folder or to ~/.miro/token, and chmod 600 it."
            )

    # ---- core -----------------------------------------------------------
    def request(self, method, path, params=None, body=None):
        method = method.upper()
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            if clean:
                url += ("&" if "?" in url else "?") + urllib.parse.urlencode(clean)

        if self.dry_run:
            return {"dry_run": True, "method": method, "url": url, "body": body}

        data = json.dumps(body).encode() if body is not None else None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"

        for attempt in range(MAX_RETRIES):
            req = urllib.request.Request(url, data=data, method=method, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    raw = resp.read().decode()
                    return json.loads(raw) if raw.strip() else {"status": resp.status, "ok": True}
            except urllib.error.HTTPError as e:
                raw = e.read().decode(errors="replace")
                if e.code == 429 or 500 <= e.code < 600:
                    if attempt < MAX_RETRIES - 1:
                        wait = float(e.headers.get("Retry-After") or 2 ** attempt)
                        time.sleep(min(wait, 60))
                        continue
                try:
                    parsed = json.loads(raw)
                except ValueError:
                    parsed = raw
                raise MiroError(e.code, parsed, method, url) from None
            except urllib.error.URLError as e:
                raise MiroError(0, f"Network error: {e.reason} (is api.miro.com reachable?)", method, url) from None
        raise MiroError(429, "Retries exhausted", method, url)

    def get(self, path, **params):
        return self.request("GET", path, params=params)

    # ---- pagination -----------------------------------------------------
    def paginate_cursor(self, path, limit=50, **params):
        """Items-style endpoints: response has data[] and cursor."""
        out, cursor = [], None
        while True:
            page = self.get(path, limit=limit, cursor=cursor, **params)
            if self.dry_run:
                return page
            out.extend(page.get("data", []))
            cursor = page.get("cursor")
            if not cursor:
                return out

    def paginate_offset(self, path, limit=50, **params):
        """Boards/members-style endpoints: response has data[], total, offset."""
        out, offset = [], 0
        while True:
            page = self.get(path, limit=limit, offset=offset, **params)
            if self.dry_run:
                return page
            batch = page.get("data", [])
            out.extend(batch)
            offset += len(batch)
            if not batch or offset >= page.get("total", 0):
                return out

    # ---- identity -------------------------------------------------------
    def whoami(self):
        info = self.get("/v1/oauth-token")
        if isinstance(info, dict):
            info["token_source"] = self.token_source
        return info

    # ---- boards ---------------------------------------------------------
    def list_boards(self, query=None, team_id=None, all_pages=False, limit=20):
        if all_pages:
            return self.paginate_offset("/v2/boards", query=query, team_id=team_id)
        return self.get("/v2/boards", query=query, team_id=team_id, limit=limit)

    def get_board(self, board):
        return self.get(f"/v2/boards/{enc(board)}")

    def create_board(self, name, description=None, team_id=None, policy=None):
        body = {"name": name}
        if description is not None:
            body["description"] = description
        if team_id:
            body["teamId"] = team_id
        if policy:
            body["policy"] = policy
        return self.request("POST", "/v2/boards", body=body)

    def update_board(self, board, name=None, description=None, policy=None, team_id=None, project_id=None):
        body = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if policy:
            body["policy"] = policy
        if team_id:
            body["teamId"] = team_id
        if project_id:
            body["projectId"] = project_id
        if not body:
            raise SystemExit("Nothing to update: pass at least one field.")
        return self.request("PATCH", f"/v2/boards/{enc(board)}", body=body)

    def copy_board(self, board, name=None, description=None, team_id=None):
        body = {k: v for k, v in {"name": name, "description": description, "teamId": team_id}.items() if v}
        return self.request("PUT", "/v2/boards", params={"copy_from": board_id_from(board)}, body=body or {})

    def copy_board_v1(self, board, name=None):
        """Copy a board WITH full content via the v1 endpoint. Use this for rich
        templates: v2 copy_from can return success but create a blank board.
        v1 names the copy 'Copy of ...', so pass name to rename it afterwards."""
        copy = self.request("POST", f"/v1/boards/{enc(board)}/copy")
        if name and not self.dry_run and copy.get("id"):
            self.update_board(copy["id"], name=name)
            copy["name"] = name
        return copy

    def delete_board(self, board):
        return self.request("DELETE", f"/v2/boards/{enc(board)}")

    # ---- members --------------------------------------------------------
    def list_members(self, board):
        return self.paginate_offset(f"/v2/boards/{enc(board)}/members")

    def share_board(self, board, emails, role="editor", message=None):
        body = {"emails": list(emails), "role": role}
        if message:
            body["message"] = message
        return self.request("POST", f"/v2/boards/{enc(board)}/members", body=body)

    def update_member(self, board, member_id, role):
        return self.request("PATCH", f"/v2/boards/{enc(board)}/members/{member_id}", body={"role": role})

    def remove_member(self, board, member_id):
        return self.request("DELETE", f"/v2/boards/{enc(board)}/members/{member_id}")

    # ---- items ----------------------------------------------------------
    def list_items(self, board, item_type=None, parent_item_id=None, all_pages=True):
        path = f"/v2/boards/{enc(board)}/items"
        params = {"type": item_type, "parent_item_id": parent_item_id}
        if all_pages:
            return self.paginate_cursor(path, **params)
        return self.get(path, limit=50, **params)

    def get_item(self, board, item_id):
        return self.get(f"/v2/boards/{enc(board)}/items/{item_id}")

    def update_item(self, board, item_id, item_type=None, body=None):
        """Generic PATCH. item_type like 'sticky_notes' hits the typed endpoint
        (needed for data/style changes); omit it for position/parent-only moves."""
        seg = item_type or "items"
        return self.request("PATCH", f"/v2/boards/{enc(board)}/{seg}/{item_id}", body=body or {})

    def delete_item(self, board, item_id):
        return self.request("DELETE", f"/v2/boards/{enc(board)}/items/{item_id}")

    def create_item(self, board, item_type, body):
        """item_type is the plural path segment: sticky_notes, cards, app_cards,
        shapes, texts, frames, images, documents, embeds, connectors."""
        return self.request("POST", f"/v2/boards/{enc(board)}/{item_type}", body=body)

    # ---- tags -----------------------------------------------------------
    def list_tags(self, board):
        return self.paginate_offset(f"/v2/boards/{enc(board)}/tags")

    def create_tag(self, board, title, fill_color=None):
        body = {"title": title}
        if fill_color:
            body["fillColor"] = fill_color
        return self.request("POST", f"/v2/boards/{enc(board)}/tags", body=body)

    def attach_tag(self, board, item_id, tag_id):
        return self.request("POST", f"/v2/boards/{enc(board)}/items/{item_id}", params={"tag_id": tag_id})

    def detach_tag(self, board, item_id, tag_id):
        return self.request("DELETE", f"/v2/boards/{enc(board)}/items/{item_id}", params={"tag_id": tag_id})

    def delete_tag(self, board, tag_id):
        return self.request("DELETE", f"/v2/boards/{enc(board)}/tags/{tag_id}")


# ---- CLI --------------------------------------------------------------------
def _kv(pairs):
    out = {}
    for p in pairs or []:
        if "=" not in p:
            raise SystemExit(f"--param expects key=value, got: {p}")
        k, v = p.split("=", 1)
        out[k] = v
    return out


def _json_arg(s):
    if s is None:
        return None
    if s.startswith("@"):
        with open(s[1:]) as f:
            return json.load(f)
    return json.loads(s)


def _confirm(args, what):
    if not args.yes and not args.dry_run:
        raise SystemExit(f"Refusing to {what} without --yes. Re-run with --dry-run first to preview.")


def build_parser():
    p = argparse.ArgumentParser(description="Miro REST API v2 CLI", formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--dry-run", action="store_true", help="Print the request instead of sending it")
    sub = p.add_subparsers(dest="group", required=True)

    sub.add_parser("whoami", help="Show token owner, team, and scopes")

    b = sub.add_parser("board").add_subparsers(dest="cmd", required=True)
    x = b.add_parser("list"); x.add_argument("--query"); x.add_argument("--team-id"); x.add_argument("--all", action="store_true")
    x = b.add_parser("get"); x.add_argument("board")
    x = b.add_parser("create"); x.add_argument("--name", required=True); x.add_argument("--description"); x.add_argument("--team-id"); x.add_argument("--policy", help="JSON policy object")
    x = b.add_parser("update"); x.add_argument("board"); x.add_argument("--name"); x.add_argument("--description"); x.add_argument("--policy", help="JSON policy object"); x.add_argument("--team-id", help="Move board to team"); x.add_argument("--project-id", help="Move board to project/space")
    x = b.add_parser("rename"); x.add_argument("board"); x.add_argument("name")
    x = b.add_parser("copy"); x.add_argument("board"); x.add_argument("--name"); x.add_argument("--description"); x.add_argument("--team-id")
    x = b.add_parser("copy-v1", help="Copy with full content via v1 (use for rich templates)"); x.add_argument("board"); x.add_argument("--name")
    x = b.add_parser("delete"); x.add_argument("board"); x.add_argument("--yes", action="store_true")

    m = sub.add_parser("members").add_subparsers(dest="cmd", required=True)
    x = m.add_parser("list"); x.add_argument("board")
    x = m.add_parser("share"); x.add_argument("board"); x.add_argument("emails", nargs="+"); x.add_argument("--role", default="editor", choices=["viewer", "commenter", "editor", "coowner", "owner"]); x.add_argument("--message")
    x = m.add_parser("update"); x.add_argument("board"); x.add_argument("member_id"); x.add_argument("--role", required=True)
    x = m.add_parser("remove"); x.add_argument("board"); x.add_argument("member_id"); x.add_argument("--yes", action="store_true")

    i = sub.add_parser("items").add_subparsers(dest="cmd", required=True)
    x = i.add_parser("list"); x.add_argument("board"); x.add_argument("--type", help="sticky_note, frame, card, shape, text, ..."); x.add_argument("--parent", help="Frame ID to list children of"); x.add_argument("--all", action="store_true", help="Follow cursor pagination")
    x = i.add_parser("get"); x.add_argument("board"); x.add_argument("item_id")
    x = i.add_parser("create"); x.add_argument("board"); x.add_argument("item_type", help="Plural path segment, e.g. sticky_notes"); x.add_argument("--data", required=True, help="JSON body or @file.json")
    x = i.add_parser("update"); x.add_argument("board"); x.add_argument("item_id"); x.add_argument("--type", dest="item_type", help="Plural segment for typed PATCH, e.g. sticky_notes"); x.add_argument("--data", required=True, help="JSON body or @file.json")
    x = i.add_parser("delete"); x.add_argument("board"); x.add_argument("item_id"); x.add_argument("--yes", action="store_true")

    t = sub.add_parser("tags").add_subparsers(dest="cmd", required=True)
    x = t.add_parser("list"); x.add_argument("board")
    x = t.add_parser("create"); x.add_argument("board"); x.add_argument("title"); x.add_argument("--color", help="e.g. red, light_green, blue")
    x = t.add_parser("attach"); x.add_argument("board"); x.add_argument("item_id"); x.add_argument("tag_id")
    x = t.add_parser("detach"); x.add_argument("board"); x.add_argument("item_id"); x.add_argument("tag_id")
    x = t.add_parser("delete"); x.add_argument("board"); x.add_argument("tag_id"); x.add_argument("--yes", action="store_true")

    r = sub.add_parser("request", help="Call any endpoint. '{board}' in path is replaced with --board (encoded).")
    r.add_argument("method"); r.add_argument("path"); r.add_argument("--board"); r.add_argument("--param", action="append", help="key=value (repeatable)"); r.add_argument("--data", help="JSON body or @file.json"); r.add_argument("--yes", action="store_true")
    return p


def run(args):
    c = MiroClient(dry_run=args.dry_run)
    g, cmd = args.group, getattr(args, "cmd", None)

    if g == "whoami":
        return c.whoami()

    if g == "board":
        if cmd == "list":   return c.list_boards(args.query, args.team_id, all_pages=args.all)
        if cmd == "get":    return c.get_board(args.board)
        if cmd == "create": return c.create_board(args.name, args.description, args.team_id, _json_arg(args.policy))
        if cmd == "update": return c.update_board(args.board, args.name, args.description, _json_arg(args.policy), args.team_id, args.project_id)
        if cmd == "rename": return c.update_board(args.board, name=args.name)
        if cmd == "copy":   return c.copy_board(args.board, args.name, args.description, args.team_id)
        if cmd == "copy-v1": return c.copy_board_v1(args.board, args.name)
        if cmd == "delete": _confirm(args, "delete a board"); return c.delete_board(args.board)

    if g == "members":
        if cmd == "list":   return c.list_members(args.board)
        if cmd == "share":  return c.share_board(args.board, args.emails, args.role, args.message)
        if cmd == "update": return c.update_member(args.board, args.member_id, args.role)
        if cmd == "remove": _confirm(args, "remove a board member"); return c.remove_member(args.board, args.member_id)

    if g == "items":
        if cmd == "list":   return c.list_items(args.board, args.type, args.parent, all_pages=args.all)
        if cmd == "get":    return c.get_item(args.board, args.item_id)
        if cmd == "create": return c.create_item(args.board, args.item_type, _json_arg(args.data))
        if cmd == "update": return c.update_item(args.board, args.item_id, args.item_type, _json_arg(args.data))
        if cmd == "delete": _confirm(args, "delete an item"); return c.delete_item(args.board, args.item_id)

    if g == "tags":
        if cmd == "list":   return c.list_tags(args.board)
        if cmd == "create": return c.create_tag(args.board, args.title, args.color)
        if cmd == "attach": return c.attach_tag(args.board, args.item_id, args.tag_id)
        if cmd == "detach": return c.detach_tag(args.board, args.item_id, args.tag_id)
        if cmd == "delete": _confirm(args, "delete a tag"); return c.delete_tag(args.board, args.tag_id)

    if g == "request":
        path = args.path
        if "{board}" in path:
            if not args.board:
                raise SystemExit("Path contains {board}; pass --board <url|id>.")
            path = path.replace("{board}", enc(args.board))
        if args.method.upper() == "DELETE":
            _confirm(args, "send a DELETE")
        return c.request(args.method, path, params=_kv(args.param), body=_json_arg(args.data))

    raise SystemExit("Unknown command")


def main():
    args = build_parser().parse_args()
    try:
        result = run(args)
    except MiroError as e:
        print(json.dumps({"error": True, "status": e.status, "method": e.method, "url": e.url, "body": e.body}, indent=2), file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
