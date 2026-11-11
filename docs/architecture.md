# Architecture

GitHub renders the Mermaid diagrams below natively.

## 1. Where the client sits

```mermaid
flowchart LR
    U["You"] --> C["Claude<br/>(Claude Code / Cowork)"]
    C -- "MCP first" --> MCP["Miro MCP connector<br/>read boards, diagrams, tables, docs"]
    C -- "gaps: copy, share, delete,<br/>move, tags, policy, admin" --> SK["miro-rest-api skill<br/>SKILL.md routing rules"]
    SK --> CL["miro_api.py<br/>MiroClient + CLI"]
    TOK[("Token<br/>MIRO_TOKEN / ~/.miro/token")] --> CL
    CL -- "HTTPS Bearer" --> API["Miro REST API<br/>v1, v2, Enterprise v2/orgs"]
    MCP --> API
    APP["Miro app(s)<br/>scoped, revocable"] -. "issues" .-> TOK
    API --> OBJ["Boards, items, members,<br/>tags, spaces, policies"]
```

## 2. Request pipeline inside the client

```mermaid
flowchart TD
    A["CLI args or MiroClient call"] --> B["Resolve token<br/>env, file env, ./.miro_token, ~/.miro/token"]
    B --> C["Normalize board ref<br/>URL to ID, URL-encode '='"]
    C --> D{"--dry-run?"}
    D -- yes --> E["Return method, url, body<br/>no network"]
    D -- no --> F["HTTP request + Bearer header"]
    F --> G{"Status"}
    G -- "429 / 5xx" --> H["Backoff, Retry-After, up to 5 tries"] --> F
    G -- "2xx" --> I["Parse JSON, paginate if needed"]
    G -- "4xx" --> J["MiroError: JSON on stderr, exit 1"]
    I --> K["JSON on stdout"]
```

## 3. Routing decision

```mermaid
flowchart TD
    Q["User asks for a Miro change"] --> M{"MCP tool exists<br/>and works?"}
    M -- yes --> MCPUSE["Use MCP"]
    M -- no --> R{"Destructive or bulk?"}
    R -- yes --> DR["Run --dry-run, show plan,<br/>get confirmation, then --yes"]
    R -- no --> RUN["Run REST command"]
    DR --> RUN
    RUN --> PREV["Preview result with MCP board_show"]
```

## 4. Capability map

```mermaid
flowchart LR
    CL["miro_api.py"] --> Bd["board: list get create update rename copy copy-v1 delete"]
    CL --> Mb["members: list share update remove"]
    CL --> It["items: list get create update delete"]
    CL --> Tg["tags: list create attach detach delete"]
    CL --> Rq["request: any endpoint<br/>(v1, v2, /v2/orgs/... admin)"]
```

## 5. Setup flow

```mermaid
sequenceDiagram
    actor D as You
    participant Mi as Miro (Your apps)
    participant Ad as Org admin
    participant FS as ~/.miro/token
    participant CC as Claude Code
    D->>Mi: Create app, pick team, set scopes
    opt org requires approval
        Mi->>Ad: Approval request
        Ad-->>Mi: Approve
    end
    D->>Mi: Install app, get OAuth token
    D->>FS: Save token (chmod 600), never in chat
    D->>CC: Install skill folder in ~/.claude/skills
    CC->>FS: client reads token at run time
    CC->>Mi: whoami check, then real work
```
