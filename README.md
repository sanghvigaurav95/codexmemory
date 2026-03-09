# CodexMemory — 100x AI-Powered Semantic Code Memory

A self-healing, auto-indexing AI memory engine that gives your IDE superpowers. It understands your entire codebase and lets you search it using natural language — instantly.

---

## How It Works (Simple English)

### 1. You Open a Project in Your IDE

When your IDE (like Cursor or Antigravity) starts, it launches the CodexMemory MCP server in the background. The server does **one smart thing** immediately:

**It figures out which project you're working in.**

It does this by looking at the current directory and walking **upward** through the folder tree until it finds a project root marker — things like:

| Marker | Language |
|--------|----------|
| `.git` | Any (Git repo) |
| `requirements.txt` | Python |
| `package.json` | JavaScript/Node |
| `setup.py` / `pyproject.toml` | Python |
| `Cargo.toml` | Rust |
| `go.mod` | Go |
| `pom.xml` / `build.gradle` | Java |
| `Gemfile` | Ruby |

For example, if your project lives at `C:\MyWebsite` and has a `package.json` inside it, CodexMemory will detect `C:\MyWebsite` as the project root — even if your terminal is currently inside `C:\MyWebsite\src\components`.

---

### 2. Brand New Project (No Index Exists)

If CodexMemory has **never seen this project before**, it checks for a hidden folder called `.codexmemory` inside the project root.

**If `.codexmemory` doesn't exist → Automatic Full Build:**

1. **Scans** every file in your project (Python, JS, Java, Ruby, Go, Rust, C++, JSON, Markdown, etc.)
2. **Parses** the code structure — extracts every class, function, method, and their relationships
3. **Chunks** the code into smart semantic blocks (not random 500-character splits, but actual logical code boundaries)
4. **Embeds** each chunk into a mathematical AI vector using MiniLM
5. **Saves** everything into a hidden `.codexmemory/` folder inside your project:
   - `project_index.faiss` — The AI vector database
   - `project_metadata.pkl` — Chunk-level metadata
   - `project_deps.pkl` — Import/dependency graph
   - `project_structure.pkl` — Classes, functions, signatures
   - `synaptic_grid.dat` — Binary AST pointer grid
   - `file_registry.json` — File path registry

This happens **automatically** the first time you open a project. You don't need to run any commands.

---

### 3. Existing Project (Index Already Built)

If CodexMemory finds the `.codexmemory/` folder already exists with a valid `project_index.faiss` file:

**It skips the full build entirely** and loads the pre-built index into RAM instantly.

Then it starts the **Nervous System** — a background watchdog daemon that listens to your OS for file changes in real-time:

| Event | What Happens |
|-------|-------------|
| **You edit a file and save** | The daemon detects the change, waits 2 seconds (to batch rapid saves), then surgically updates only that file's vectors in the FAISS index. No full rebuild. |
| **You create a new file** | The daemon detects the creation, parses and indexes it automatically. |
| **You delete a file** | The daemon detects the deletion and marks its vectors as deleted to prevent stale results. |

This means your AI memory is **always up to date** without you doing anything.

---

### 4. Moving to a New Computer

If you get a new PC and clone this repository:

1. **Install dependencies:**
   ```bash
   cd codexmemory
   pip install -e .
   ```

2. **Auto-generate your IDE config:**
   ```bash
   python src/tools/install_mcp.py
   ```
   This automatically:
   - Detects your Python virtual environment path
   - Finds the `mcp_server.py` location
   - Writes the perfect `mcp_config.json` into your IDE's config folder
   - Merges with any existing MCP servers you have configured

3. **Restart your IDE** — CodexMemory is ready.

---

## The 3 Search Tools

Once running, CodexMemory gives your AI assistant 3 tools:

### `resonance_search` (Use 95% of the time)
Ask any question in natural language. Returns the exact code chunk that answers it.
- **Cost:** ~500 tokens
- **Example:** *"How does the login authentication work?"*

### `inspect_canvas` (Use 4% of the time)
Returns the full source code of a specific file with its blueprint and dependency graph.
- **Cost:** ~2,000-5,000 tokens
- **Use when:** You need to rewrite an entire file

### `deep_search` (Use 1% of the time)
Returns multiple matching files with their full source code.
- **Cost:** ~10,000+ tokens
- **Use when:** Complex cross-file refactoring

---

## Supported File Types

CodexMemory indexes **40+ file extensions** across all major languages:

| Category | Extensions |
|----------|-----------|
| Python | `.py`, `.pyi`, `.pyx` |
| JavaScript/TypeScript | `.js`, `.jsx`, `.ts`, `.tsx`, `.mjs`, `.cjs` |
| Web | `.html`, `.css`, `.scss`, `.vue`, `.svelte` |
| Systems | `.c`, `.cpp`, `.h`, `.rs`, `.go`, `.swift` |
| JVM | `.java`, `.kt`, `.kts` |
| Scripting | `.rb`, `.php`, `.lua`, `.dart` |
| Config/Data | `.json`, `.yaml`, `.toml`, `.xml`, `.env` |
| Documentation | `.md`, `.txt`, `.rst`, `.csv` |
| Build | `.gradle`, `.cmake`, `.dockerfile` |
| Other | `.sql`, `.graphql`, `.proto` |

Binary files (images, databases, compiled files) are **automatically ignored**.

---

## Project Structure

```
codexmemory/
├── setup.py                     # PIP installer
├── requirements.txt             # Python dependencies
├── .codexmemory/                # Auto-generated AI database (hidden)
│   ├── project_index.faiss      # FAISS vector index
│   ├── project_metadata.pkl     # Chunk metadata
│   ├── project_deps.pkl         # Dependency graph
│   ├── project_structure.pkl    # Code structure map
│   ├── synaptic_grid.dat        # Binary AST grid
│   └── file_registry.json       # File path registry
└── src/
    └── tools/
        ├── mcp_server.py        # MCP server (entry point)
        ├── project_memory.py    # Core indexing engine
        ├── project_search.py    # Search & retrieval engine
        ├── synaptic_router.py   # Binary grid + file watcher
        └── install_mcp.py       # Auto-config generator
```

---

## Quick Reference

| Scenario | What Happens |
|----------|-------------|
| First time opening a project | Auto-builds the full FAISS index |
| Opening a project that was indexed before | Loads from `.codexmemory/` instantly |
| Editing and saving a file | Surgically updates only that file's vectors |
| Creating a new file | Auto-indexes it within 2 seconds |
| Deleting a file | Marks its vectors as deleted |
| Moving to a new PC | Run `install_mcp.py` once, restart IDE |
| Changing Python environments | Run `install_mcp.py` again to update paths |
