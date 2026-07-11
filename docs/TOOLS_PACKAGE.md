# 🔧 Tools Package

The `tools` package provides custom LangChain tools that enable the AI agent to interact with the filesystem, execute terminal commands, and perform other operations beyond pure reasoning. These tools extend the agent's capabilities to actually manipulate and explore the codebase and system environment.

## 📁 Package Structure

```
educosys_claude/tools/
├── __init__.py
├── filesystem_tools.py  # File system operations (read, write, etc.)
└── terminal_tools.py    # Terminal/command execution
```

## 🧩 Components

### 1. Filesystem Tools (`filesystem_tools.py`)

**Purpose**: Provides tools for safe filesystem operations including reading, writing, appending, deleting files, listing directories, and checking file existence.

**Key Tools** (all decorated with `@tool` from LangChain):
- `read_file(file_path: str) -> str`: Read and return file contents
- `write_file(file_path: str, content: str) -> str`: Write content to a file (creates directories if needed)
- `append_file(file_path: str, content: str) -> str`: Append content to an existing file
- `delete_file(file_path: str) -> str`: Delete a file
- `list_directory(directory: str) -> str`: List files and subdirectories in a directory
- `file_exists(file_path: str) -> str`: Check if a file or directory exists

**Safety Features**:
- Path validation (empty/null checks)
- File type verification (ensures paths are files when expected)
- Directory verification (ensures paths are directories when expected)
- Size limits (10MB max for read operations)
- UTF-8 validation for text files
- Permission error handling
- Comprehensive exception handling with informative error messages

**Return Values**:
- Success: Descriptive message (e.g., "Written to /path/to/file")
- Error: Clear error message starting with "Error:" for agent interpretation

### 2. Terminal Tools (`terminal_tools.py`)

**Purpose**: Provides tools for executing shell commands with security restrictions and timeout protection.

**Key Tools**:
- `run_command(command: str) -> str`: Execute a shell command and return its output
- `run_in_directory(command: str, directory: str) -> str`: Execute a shell command within a specific directory

**Security Features**:
- Blocked command prevention: Prevents execution of dangerous commands like:
  - `rm -rf /` (attempt to delete root filesystem)
  - `mkfs` (filesystem formatting)
  - `dd if=` (disk duplication commands)
  - `:(){:|:&};:` (fork bomb)
- Timeout protection: All commands timeout after 30 seconds
- Input validation: Rejects empty commands or directories
- Path validation: Verifies directory exists and is actually a directory

**Output Formatting**:
- Captures both stdout and stderr
- Includes exit code if non-zero
- Returns formatted string with clear separation of output streams
- Handles timeout and exception cases gracefully

## 🝱 Integration with Human-in-the-Loop (HITL)

**Critical**: The following tools are **DANGEROUS** and require human approval before execution via the HITL middleware in `agent/factory.py`:

| Tool | Category | Risk |
|------|----------|------|
| `run_command` | Terminal | Arbitrary shell command execution |
| `run_in_directory` | Terminal | Arbitrary command in specific dir |
| `write_file` | Filesystem | Creates/overwrites files |
| `append_file` | Filesystem | Modifies existing files |
| `delete_file` | Filesystem | Permanently removes files |

**How it works**:
1. Agent calls a dangerous tool (e.g., `run_command('git push')`)
2. `HumanInTheLoopMiddleware` intercepts → **pauses graph execution**
3. **Local terminal**: `rich.Prompt` asks `Approve / Edit / Reject?`
4. **GitHub Actions**: Bot posts comment to Issue/Gist → polls for `/APPROVE`, `/REJECT`, `/EDIT`
5. On decision: `Command(resume={"decisions": [...]})` resumes agent
6. `PatchToolCallsMiddleware` cleans orphaned `tool_calls` from history
7. Tool actually executes

See `agent/hitl_github_actions.py` for GitHub Actions workflow integration.

## 🔧 How It Works Together

### Tool Usage Flow
```
Agent Decision Process
     ↓
Agent decides it needs to perform filesystem or terminal operation
     ↓
Agent calls appropriate tool (e.g., read_file, run_command)
     ↓
Tool executes with safety checks:
     ↓
   1. Input validation (non-empty, proper types)
   2. Path/directory validation
   3. Security checks (blocked commands, etc.)
   4. Operation execution
   5. Result formatting
   6. Error handling and messaging
     ↓
Tool returns string result to agent
     ↓
Agent incorporates result into reasoning and response generation
```

### Filesystem Tool Example (`read_file`)
```
1. Agent calls: read_file("/path/to/file.py")
   ↓
2. Validate: file_path not empty
   ↓
3. Check: os.path.exists(file_path)
   ↓
4. Check: os.path.isfile(file_path) (not a directory)
   ↓
5. Check: file size < 10MB
   ↓
6. Try to open and read with UTF-8 encoding
   ↓
7. On success: return file contents
   ↓
8. On failure: return appropriate error message
```

### Terminal Tool Example (`run_command`)
```
1. Agent calls: run_command("ls -la")
   ↓
2. Validate: command not empty
   ↓
3. Check: command not in blocked list
   ↓
4. Try to run with subprocess.run():
   ↓
   - shell=True
   - capture_output=True
   - text=True
   - timeout=30 seconds
   ↓
5. On completion:
   ↓
   - If stdout: include in result
   ↓
   - If stderr: include as "STDERR: ..."
   ↓
   - If returncode != 0: include "Exit code: X"
   ↓
6. Format and return combined output
   ↓
7. On timeout: return timeout error message
   ↓
8. On exception: return error message
```

## ⚙️ Configuration

The tools package has limited direct configuration but does use some constants:

### Filesystem Tools Configuration (`filesystem_tools.py`)
- `_MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024` (10 MB)
  - Controls maximum file size for read operations
  - Can be modified by changing this constant

### Terminal Tools Configuration (`terminal_tools.py`)
- `_BLOCKED_COMMANDS = {"rm -rf /", "mkfs", "dd if=", ":(){:|:&};:"}`
  - Set of command substrings that are blocked for security
  - Can be extended by adding to this set
- `_TIMEOUT_SECONDS = 30`
  - Maximum execution time for commands in seconds
  - Can be modified by changing this constant

## 📝 Usage Examples

### Filesystem Operations
```python
# Reading a file
result = read_file("/project/src/main.py")
# Returns: file contents or error message

# Writing a file
result = write_file("/project/src/new_feature.py", "# New feature\nprint('Hello')")
# Returns: "Written to /project/src/new_feature.py" or error

# Appending to a log file
result = append_file("/project/logs/app.log", "\n[INFO] Application started")
# Returns: "Appended to /project/logs/app.log" or error

# Listing directory contents
result = list_directory("/project/src")
# Returns: newline-separated list of files or error

# Checking if file exists
result = file_exists("/project/config.yaml")
# Returns: "True" or "False"
```

### Terminal Operations
```python
# Running a simple command
result = run_command("ls -la | head -5")
# Returns: formatted output of ls command

# Running command in specific directory
result = run_in_directory("npm install", "/project/frontend")
# Returns: formatted output of npm install in frontend directory

# Running a blocked command (returns error)
result = run_command("rm -rf /")
# Returns: "Error: command is not allowed for safety reasons"
```

## 🔄 Integration Points

The tools package is used by:
1. **Agent Package** (`agent/factory.py`):
   - All filesystem and terminal tools are included in the agent's tool list
   - Tools are passed to `create_agent()` making them available to the LLM agent
   - Agent can decide to use these tools during reasoning process

2. **Main Application** (`main.py`):
   - Indirectly through agent tool usage
   - Commands like `/show_index` don't directly use these tools but the agent might

3. **Memory Package**:
   - Potentially used indirectly if agent decides to examine memory files
   - Example: agent might use `read_file` to check `.memory/memory.db` properties

## 📊 Performance Characteristics

### Filesystem Tools
- **read_file**: O(n) where n is file size (limited to 10MB max)
- **write_file**: O(n) where n is content size
- **append_file**: O(n) where n is content size (plus seek to end)
- **delete_file**: O(1) typical filesystem operation
- **list_directory**: O(n) where n is number of directory entries
- **file_exists**: O(1) typical filesystem operation

### Terminal Tools
- **run_command**: O(t) where t is command execution time (capped at 30s)
- **run_in_directory**: Same as run_command plus directory change overhead
- **Actual performance**: Depends entirely on the command being executed

## 🛠️ Customization & Extension

### Adding New Filesystem Tools
To add a new filesystem tool:
1. Create a new function in `filesystem_tools.py`
2. Decorate with `@tool` from `langchain.tools`
3. Add input validation and safety checks
4. Implement the core functionality
5. Add appropriate error handling and return messages
6. Import and add to the agent's tool list in `agent/factory.py`

### Adding New Terminal Tools
To add a new terminal tool:
1. Create a new function in `terminal_tools.py`
2. Decorate with `@tool`
3. Add input validation (non-empty, etc.)
4. Add security checks if needed
5. Implement command execution with `_format_result`
6. Add to agent's tool list in `agent/factory.py`

### Modifying Safety Parameters
To adjust security or limits:
1. **Filesystem size limit**: Change `_MAX_FILE_SIZE_BYTES` in `filesystem_tools.py`
2. **Blocked commands**: Add/remove from `_BLOCKED_COMMANDS` set in `terminal_tools.py`
3. **Command timeout**: Change `_TIMEOUT_SECONDS` in `terminal_tools.py`

### Adding New Tool Categories
To add entirely new tool categories (e.g., database tools, API tools):
1. Create new file (e.g., `database_tools.py`)
2. Implement tools with `@tool` decorator
3. Add proper validation, error handling, and return formatting
4. Import and add to agent's tool list in `agent/factory.py`
5. Consider if any new configuration is needed in `config.yaml`

## 💡 Best Practices

### For Tool Development
1. **Always validate inputs**: Check for None, empty strings, invalid types
2. **Validate paths**: Use `os.path.exists()`, `os.path.isfile()`, `os.path.isdir()` as appropriate
3. **Handle encoding**: Always specify encoding (UTF-8 recommended) for text operations
4. **Limit resource usage**: Implement size limits, timeouts, and frequency controls where appropriate
5. **Return clear messages**: Success messages should describe what was done; error messages should start with "Error:" and be actionable
6. **Handle exceptions**: Catch specific exceptions rather than bare `except:` when possible
7. **Log appropriately**: Use the observability logger for debugging tool issues

### For Security
1. **Principle of least privilege**: Tools should only provide necessary functionality
2. **Input sanitization**: While LangChain tools handle some validation, additional checks are wise
3. **Command blocking**: For terminal tools, err on the side of blocking more rather than less
4. **Path traversal**: Be wary of `../` sequences in file paths - consider using `os.path.normpath()` and checking if result stays within allowed directories
5. **Environment isolation**: Consider running in sandboxed environments for maximum security

### For Usability
1. **Consistent return format**: All tools should return strings - either success descriptions or error messages
2. **Informative errors**: Error messages should help the agent understand what went wrong
3. **Predictable behavior**:Similar inputs should produce similar outputs
4. **Documentation**: Clear docstrings help both developers and the LLM agent understand tool purpose
5. **Atomic operations**: Where possible, make tools atomic (either fully succeed or fully fail with clear state)

## 🔄 Integration with Agent Reasoning

The tools enable powerful agent behaviors:
```
User Query: "Show me the contents of the main entry point file"
     ↓
Agent reasons: I need to find the main entry point, then read it
     ↓
Agent uses search_codebase tool (from agent/tools.py) to find main.py or similar
     ↓
Agent gets result showing main.py location and contents snippet
     ↓
Agent reasons: I should read the full file to show the user
     ↓
Agent calls read_file tool with the discovered path
     ↓
Tool returns full file contents
     ↓
Agent incorporates file contents into final response to user
```

Or:
```
User Query: "What happens when I run the test suite?"
     ↓
Agent reasons: I need to find test commands and potentially run them
     ↓
Agent searches for test-related files (pytest, unittest, etc.)
     ↓
Agent finds test runner script or configuration
     ↓
Agent reasons: I should run the tests to see what happens
     ↓
Agent calls run_command or run_in_directory with test command
     ↓
Tool executes tests and returns output
     ↓
Agent analyzes test output and reports results to user
```

## 🛡️ Safety Considerations

### Filesystem Safety
1. **Path confinement**: While not implemented, production systems might want to confine operations to project directory
2. **Symlink handling**: Current implementation follows symlinks - consider if this is desired behavior
3. **File type verification**: Tools verify they're operating on expected file types (not directories for file ops, etc.)
4. **Size limits**: Prevents attempting to read enormous files into memory

### Terminal Safety
1. **Command blocking**: Explicit prevention of known dangerous commands
2. **Timeout protection**: Prevents hanging commands from blocking the agent indefinitely
3. **Output capture**: Prevents commands from inadvertently affecting terminal state
4. **No shell injection**: While using `shell=True`, the input validation and blocked list help prevent injection
5. **Working directory control**: `run_in_directory` allows specifying safe working directories

### Potential Enhancements
1. **Project confinement**: Add optional base directory restriction for all file operations
2. **Audit logging**: Log all tool usages for security review
3. **Rate limiting**: Prevent excessive tool use in short time periods
4. **Allow/deny lists**: More sophisticated command/FilePath filtering
5. **Return type variation**: Consider returning structured data for programmatic use (though current string format works well with LLMs)