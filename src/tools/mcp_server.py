import sys
import os
import contextlib
import io
from pathlib import Path
from mcp.server.fastmcp import FastMCP

# Ensure the parent directory is in the system path so we can import project modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from project_search import CodexResonanceSearch
from project_memory import ProjectMemory

# Create the MCP Server instance
mcp = FastMCP("CodexMemory Resonance Server")

try:
    with open(r"C:\Users\gauravsanghvi\codex_mcp_debug.txt", "a") as f:
        f.write(f"MCP Server Booted. CWD: {os.getcwd()}\n")
except:
    pass

# ============================================================================
# ORCHESTRATION SINGLETONS — Zero-Disk I/O after boot.
# ============================================================================
_memory_instance = None
_retriever_instance = None

def _get_memory(project_dir: str = None) -> ProjectMemory:
    """Returns a singleton ProjectMemory. Suppresses stdout to protect MCP JSON-RPC."""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = ProjectMemory(root_dir=project_dir)
        with contextlib.redirect_stdout(io.StringIO()):
            _memory_instance.load_full()
            
        # Start Nervous System for Delta Routing
        from synaptic_router import NervousSystem
        ns = NervousSystem(str(_memory_instance.root_dir), memory_engine=_memory_instance)
        ns.start()
        _memory_instance.nervous_system = ns # Keep reference alive
        
    return _memory_instance

def _get_retriever(project_dir: str = None) -> CodexResonanceSearch:
    """Returns a singleton CRR engine, sharing the memory instance."""
    global _retriever_instance
    if _retriever_instance is None:
        mem = _get_memory(project_dir)
        with contextlib.redirect_stdout(io.StringIO()):
            _retriever_instance = CodexResonanceSearch(memory=mem)
    return _retriever_instance


# ============================================================================
# TOOL 1: resonance_search (The Scalpel - 95% of queries)
# ============================================================================
@mcp.tool()
def resonance_search(query: str, top_k: int = 4, project_dir: str = None) -> str:
    """
    🔴 PRIMARY DEFAULT TOOL - ALWAYS USE THIS FIRST. 🔴
    
    Executes a Codex Resonance Retrieval (CRR). It returns exact 'Holographic Splices' 
    (the exact semantic code chunk + injected cross-file dependencies).
    
    WHEN TO USE:
    - 95% of your queries.
    - Conceptual questions ("How does the database connect?").
    - Finding specific logic, variables, or functions.
    
    WHY: This costs ~500 tokens. It isolates the exact logic without reading whole files.
    Do NOT use deep_search or inspect_canvas for basic questions.
    
    Args:
        query: The semantic search query (e.g. 'how does authentication work')
        top_k: Number of splices to return. Max 4.
        project_dir: MANDATORY ABSOLUTE PATH to the user's project workspace (e.g. 'E:/work/youtube'). You MUST provide this exactly.
    """
    try:
        retriever = _get_retriever(project_dir)
        results = retriever.search(query, top_k)

        if not results:
            return f"No resonance splices found for '{query}'."

        md = f"## 🌌 CRR Resonance Search: '{query}'\n\n"
        
        for i, r in enumerate(results, 1):
            md += f"### {i}. `{r['path']}` (Chunk #{r['chunk_id']})\n"
            md += f"*Fusion Score: {r['fusion_score']:.4f} | Context: {r['file_summary']}*\n\n"
            md += f"```python\n{r['content']}\n```\n\n"
            md += "---\n"
            
        return md
    except Exception as e:
        return f"Error executing resonance search: {e}"


# ============================================================================
# TOOL 2: inspect_canvas (The Wide Lens - 4% of queries)
# ============================================================================
@mcp.tool()
def inspect_canvas(file_path: str, project_dir: str = None) -> str:
    """
    🟡 SECONDARY TOOL - USE ONLY WHEN YOU KNOW THE EXACT FILE. 🟡
    
    Returns the FULL content of a single file, its structural blueprint, and dependency graph.
    
    WHEN TO USE:
    - You already used `resonance_search` and now need to rewrite the entire file.
    - You need to see the exact line numbers to propose a large git diff/patch.
    - You are debugging a syntax error and need the full top-to-bottom context.
    
    WARNING: Costs ~2,000 to 5,000 tokens per call. Do not use for general searching.
    
    Args:
        file_path: Exact or partial relative path (e.g., 'src/api.py')
        project_dir: MANDATORY ABSOLUTE PATH to the user's project workspace.
    """
    try:
        mem = _get_memory(project_dir)
        
        # Path resolution logic
        normalized = file_path.replace('\\', '/').replace('/', os.sep)
        file_path_to_read = None
        
        # We don't have file_contents anymore. We use struct code_structure keys as the file list.
        if file_path in mem.code_structure:
            file_path_to_read = file_path
        elif normalized in mem.code_structure:
            file_path_to_read = normalized
        else:
            for stored_path in mem.code_structure.keys():
                if stored_path.endswith(file_path):
                    file_path_to_read = stored_path
                    break

        if not file_path_to_read:
            return f"File '{file_path}' not found in the CodexMemory index."
            
        file_path = file_path_to_read
        full_path = mem.root_dir / file_path
        try:
            content = full_path.read_bytes().decode('utf-8', errors='ignore')  # Binary decode preserves \r\n
        except Exception as e:
            return f"Error reading file '{file_path}': {e}"

        # 1. Build the Canvas (Source Code)
        lines = content.split('\n')
        numbered_content = '\n'.join([f"{i+1:>4}: {line}" for i, line in enumerate(lines)])

        output = f"## 🎨 Canvas: `{file_path}` ({len(lines)} lines)\n\n"

        # 2. Add the Blueprint (Code Structure & Dependencies)
        struct = mem.code_structure.get(file_path, {})
        if struct and struct.get('summary'):
            output += f"### 🏗️ Blueprint\n**Summary:** {struct['summary']}\n\n"

        deps = mem.dependency_graph.get(file_path, {})
        imports = deps.get('imports', [])
        imported_by = deps.get('imported_by', [])
        
        if imports or imported_by:
            output += "### 🔗 Resonance Threads\n"
            if imports:
                output += f"- **Imports:** {', '.join(f'`{i}`' for i in imports)}\n"
            if imported_by:
                output += f"- **Imported By:** {', '.join(f'`{i}`' for i in imported_by)}\n"
            output += "\n"

        # 3. Attach the Code
        output += f"### 📝 Source Code\n```python\n{numbered_content}\n```\n"
        return output

    except Exception as e:
        return f"Error inspecting canvas: {str(e)}"


# ============================================================================
# TOOL 3: deep_search (The Atomic Bomb - 1% of queries)
# ============================================================================
@mcp.tool()
def deep_search(query: str, top_k: int = 2, project_dir: str = None) -> str:
    """
    💀 NUCLEAR OPTION - HIGH TOKEN COST. 💀
    
    Searches the memory AND returns the FULL SOURCE CODE of multiple matching files at once.
    
    WHEN TO USE:
    - ONLY for complex, cross-file architectural refactoring.
    - When you need to understand how 2 or 3 entire systems interact globally.
    
    WARNING: This can consume 10,000+ tokens in a single call. If you just need 
    to know how a specific function works, USE `resonance_search` INSTEAD.
    
    Args:
        query: The overarching cross-boundary architectural query
        top_k: Number of files to return
        project_dir: MANDATORY ABSOLUTE PATH to the user's project workspace.
    """
    try:
        mem = _get_memory(project_dir)
        retriever = _get_retriever(project_dir)
        
        results = retriever.search(query, top_k)
        if not results:
            return "No results found for the query."

        output = f"## ⚛️ Atomic Deep Search: '{query}'\n"
        output += f"*Found {len(results)} exact resonance anchors.*\n\n---\n\n"

        for rank, result in enumerate(results, 1):
            path = result['path']
            
            # 1. The Anchor Metadata
            output += f"### {rank}. 📄 `{path}`\n"
            output += f"*Relevance: {result['fusion_score']:.4f} | Blueprint: {result['file_summary']}*\n\n"

            # 2. The Holographic Splice (The exact semantic hit)
            output += "#### 🎯 The Resonance Splice (Exact Match)\n"
            output += f"```python\n{result['content']}\n```\n\n"

            # 3. The Structural Blueprint (Replacing the full source code dump)
            output += "#### 🏗️ Structural Blueprint\n"
            struct = mem.code_structure.get(path, {})
            
            def format_func(f, indent=""):
                args = f.get('args', [])
                args_str = ", ".join(args) if isinstance(args, list) else str(args)
                prefix = "async " if f.get('is_async') else ""
                res = f"{indent}- `{prefix}def {f.get('name')}({args_str})`\n"
                return res

            has_struct = False
            if struct.get("classes"):
                has_struct = True
                output += "**Classes:**\n"
                for cls in struct.get("classes", []):
                    output += f"- `class {cls.get('name')}`\n"
                    for method in cls.get("methods", []):
                        output += format_func(method, "  ")
            
            if struct.get("functions"):
                has_struct = True
                output += "**Functions:**\n"
                for func in struct.get("functions", []):
                    output += format_func(func, "")
                    
            if not has_struct and struct.get("summary"):
                has_struct = True
                output += f"**Summary:** {struct['summary']}\n"
                
            if not has_struct:
                output += "*No structural blueprint available.*\n"
            output += "\n"

            # 4. Resonance Threads (Cross-file Dependencies)
            deps = mem.dependency_graph.get(path, {})
            imports = deps.get('imports', [])
            imported_by = deps.get('imported_by', [])
            
            if imports or imported_by:
                output += "#### 🔗 Resonance Threads\n"
                if imports:
                    output += f"- **Imports:** {', '.join(f'`{i}`' for i in imports)}\n"
                if imported_by:
                    output += f"- **Imported By:** {', '.join(f'`{i}`' for i in imported_by)}\n"
                output += "\n"

            output += "---\n\n"

        return output

    except Exception as e:
        return f"Error during deep search: {str(e)}"


if __name__ == "__main__":
    # Start the server using stdio transport (required for local IDE MCP connections)
    # ALL print statements outside of contextlib redirects will break this pipe.
    mcp.run(transport='stdio')
