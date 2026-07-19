# Code Analysis Tool

A comprehensive Python code analysis and refactoring tool that generates code maps, detects issues, and provides automated refactoring capabilities.

Author: Vasiliy Zdanovskiy  
Email: vasilyvz@gmail.com

## Documentation structure

- **docs/** (root) — Main documentation: COMMANDS_GUIDE.md, COMMANDS_INDEX.md, AI_TOOL_USAGE_RULES.md, [commands/file_editing/](commands/file_editing/) (universal edit workflow), TEST_DATA_AI_RULES.md, README.md.
- **docs/reports/** — Analyses and explanations (e.g. FILE_STRUCTURE_AND_OBJECT_SCHEMA.md, COMPONENT_INTERACTION.md, LOG_WRITE_SITES.md).
- **docs/plans/** — Technical specifications and plans (mutable_cst_layer TZ/steps, cst_concept refactor plan, design).
- **docs/standards/** — Standards and rules (PYTHON_DOCSTRING_STANDARD.md, DRIVER_STANDARD.md, FILE_EDIT_WORKFLOW.yaml, LOG_IMPORTANCE_CRITERIA.md, UNIFIED_LOG_FORMAT.md, PROJECT_PATH_AND_VENV_RULES.md).
- **docs/commands/** — Per-block command docs:
  - **file_editing** (primary for view/edit), **ast**, **backup**, **code_mapper**, **code_quality**, **cst** (internal CST APIs), **database_integrity**, **database_restore**, **file_management** (lifecycle, not content edit), **log_viewer**, **project_management**, **refactor**, **repair_worker**, **search**, **vector**, **worker_management**, **worker_status**, **analysis**, **misc**
  - In each block: `README.md` (overview and command→file table), `COMMANDS.md` (index with links to per-command docs), and **one file per command** `<command_name>.md` with: purpose, arguments, return format, examples (correct and incorrect).

## Features

### Code Analysis
- **Code Mapping**: Generates comprehensive maps of classes, functions, and dependencies
- **Issue Detection**: Identifies code quality problems and violations
- **SQLite Database**: Fast indexed storage for large codebases (default)
- **YAML Export**: Optional YAML format for compatibility
- **Configurable Analysis**: Customizable file size limits and analysis parameters
- **CLI Interface**: Easy-to-use command-line interface

### Code Refactoring
- **Class Splitting**: Split large classes into smaller components
- **Superclass Extraction**: Extract common functionality into base classes
- **Class Merging**: Merge multiple classes into a single base class
- **Safety Checks**: Automatic backups, validation, and rollback on errors
- **Strict Completeness Validation**: Pre-collects all methods and properties before operation, then validates they are all present after refactoring

## Installation

### From PyPI (recommended)

```bash
pip install code-analysis-tool
```

### From source

Dependencies and metadata live in **`pyproject.toml`** (distribution name `code-analysis`). Runtime install:

```bash
git clone https://github.com/vasilyvz/code-analysis-tool.git
cd code-analysis-tool
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
# optional — pytest, black, flake8, ruff, mypy:
pip install -e ".[dev]"
```

Or: `pip install -r requirements.txt` (editable install from this repo).

## Usage

### Code Analysis

#### Basic usage

```bash
code_mapper
```

This will analyze the current directory and generate reports in the `code_analysis` folder.

#### Advanced usage

```bash
code_mapper --root-dir ./src --output-dir ./reports --max-lines 500 --verbose
```

#### Command line options

- `--root-dir, -r`: Root directory to analyze (default: current directory)
- `--output-dir, -o`: Output directory for reports (default: code_analysis)
- `--max-lines, -m`: Maximum lines per file (default: 400)
- `--verbose, -v`: Enable verbose output
- `--use-sqlite/--no-sqlite`: Use SQLite database (default: True)
- `--version`: Show version information

#### Output Files

**SQLite Mode (default):**
- `code_analysis.db`: SQLite database with all analysis data
  - Fast indexed searches
  - SQL queries for complex filtering
  - Single file storage

**YAML Mode (`--no-sqlite`):**
- `code_map.yaml`: Complete code map with classes, functions, and dependencies
- `code_issues.yaml`: Detailed report of code quality issues
- `method_index.yaml`: Index of methods organized by class

#### Detected Issues

The tool detects various code quality issues:

- Files without docstrings
- Classes without docstrings
- Methods without docstrings
- Methods with only `pass` statements
- `NotImplementedError` in non-abstract methods
- Files exceeding line limit
- Usage of `Any` type annotations
- Generic exception handling
- Invalid imports
- Imports in the middle of files

## Project Identification and Path Normalization

### Project ID Format

Each project must have a `projectid` file in its root directory. The file uses JSON format:

```json
{
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "description": "Human readable description of project"
}
```

**Fields**:
- `id` (required): UUID4 identifier for the project
- `description` (optional): Human-readable description

**Migration**: If you have old format projectid files (plain UUID4 string), use the migration script:
```bash
python scripts/migrate_projectid_to_json.py
```

### Path Normalization

The system uses unified path normalization across all components:

- **`normalize_file_path()`**: Main function for normalizing file paths with project information
  - Returns `NormalizedPath` with absolute path, project root, project ID, and relative path
  - Validates project ID from projectid file
  - Handles both absolute and relative paths

- **`find_project_root_for_path()`**: Finds project root for a given file path
  - Searches for projectid file in parent directories
  - Returns `ProjectInfo` with project root, ID, and description
  - Raises `MultipleProjectIdError` if multiple projectid files found in path

- **`normalize_path_simple()`**: Simple path normalization without project information
  - For cases where only path normalization is needed

### Project Manager

The `ProjectManager` class provides centralized project management:

```python
from code_analysis.core.project_manager import ProjectManager

manager = ProjectManager()

# Create a new project
project_info = manager.create_project(
    root_path=Path("/path/to/project"),
    description="My project",
    init_git=True  # Optional: initialize git repository
)

# Get project information
info = manager.get_project_info(project_id)

# List all projects
projects = manager.get_project_list()
```

## CST-based module composition (logical blocks)

If you want to refactor by **logical blocks** (preserving comments, moving imports to the top,
validating via `compile()`), see `docs/CST_TOOLS.md`, `docs/CST_QUERY.md` and MCP commands
`cst_apply_buffer` / `query_cst`.

## MCP Server usage (proxy vs direct)

This repository also runs an MCP server (`code-analysis-server`) via `mcp-proxy-adapter`.

### Via MCP Proxy (recommended)

- **List servers**: `mcp_MCP-Proxy-2_list_servers(filter_enabled=None)`
- **Call command** (IMPORTANT: use `server_id` + `copy_number`, NOT `server_key`):
  `mcp_MCP-Proxy-2_call_server(server_id="code-analysis-server", copy_number=1, command="get_database_status", params={"root_dir": "/abs/path"})`
- **Queued commands** (e.g. `update_indexes`) return a `job_id`; track via `queue_get_job_status` / `queue_get_job_logs`.

See `docs/MCP_PROXY_USAGE_GUIDE.md` for more details.

### Without MCP Proxy (direct)

- Inspect API schema: `GET https://<host>:<port>/openapi.json` (mTLS)
- Call commands using endpoints described in that OpenAPI schema.

## Code Refactoring

### Class Splitting

Split a large class into multiple smaller classes while maintaining functionality.

#### Example: Before

```python
class UserManager:
    """Manages user operations."""
    
    def __init__(self):
        self.username = None
        self.email = None
        self.password = None
        self.role = None
        self.permissions = []
    
    def authenticate(self, username, password):
        """Authenticate user."""
        # ... authentication logic
    
    def authorize(self, action):
        """Check user permissions."""
        # ... authorization logic
    
    def send_email(self, subject, body):
        """Send email to user."""
        # ... email logic
```

#### Configuration File (`split_config.json`)

```json
{
  "src_class": "UserManager",
  "dst_classes": {
    "UserAuth": {
      "props": ["username", "email", "password"],
      "methods": ["authenticate"]
    },
    "UserPermissions": {
      "props": ["role", "permissions"],
      "methods": ["authorize"]
    },
    "UserEmail": {
      "props": [],
      "methods": ["send_email"]
    }
  }
}
```

#### Command

```bash
# Dry run (validate without changes)
code_refactor split-class -f user_manager.py -c split_config.json --dry-run

# Perform split
code_refactor split-class -f user_manager.py -c split_config.json
```

#### Example: After

```python
class UserManager:
    """Manages user operations."""
    
    def __init__(self):
        self.userauth = UserAuth()
        self.userpermissions = UserPermissions()
        self.useremail = UserEmail()
    
    def authenticate(self, username, password):
        return self.userauth.authenticate(username, password)
    
    def authorize(self, action):
        return self.userpermissions.authorize(action)
    
    def send_email(self, subject, body):
        return self.useremail.send_email(subject, body)

class UserAuth:
    """Handles user authentication."""
    
    def __init__(self):
        self.username = None
        self.email = None
        self.password = None
    
    def authenticate(self, username, password):
        """Authenticate user."""
        # ... authentication logic

class UserPermissions:
    """Manages user permissions."""
    
    def __init__(self):
        self.role = None
        self.permissions = []
    
    def authorize(self, action):
        """Check user permissions."""
        # ... authorization logic

class UserEmail:
    """Handles user email operations."""
    
    def __init__(self):
        pass
    
    def send_email(self, subject, body):
        """Send email to user."""
        # ... email logic
```

#### Safety Features

- **Automatic Backup**: Creates backup in `.code_mapper_backups/` before changes
- **Pre-Operation Validation**: Collects all methods and properties from source class BEFORE operation
- **Configuration Validation**: Checks that all properties and methods are accounted for in config
- **Python Syntax Check**: Validates syntax after splitting
- **Strict Completeness Check**: Compares pre-collected original members with refactored code to ensure ALL are present
- **Import Validation**: Verifies module can be imported (optional, warnings only)
- **Automatic Rollback**: Restores backup if any validation fails

### Class Merging

Merge multiple classes into a single base class. This is the inverse operation of extract-superclass.

#### Example: Before

```python
class UserAuth:
    """Handles user authentication."""
    
    def __init__(self):
        self.username = None
        self.password = None
    
    def login(self, username, password):
        """Authenticate user."""
        # ... login logic
        return True

class UserProfile:
    """Handles user profile operations."""
    
    def __init__(self):
        self.email = None
        self.name = None
    
    def update_profile(self, email, name):
        """Update user profile."""
        # ... profile logic
        return True

class UserSettings:
    """Handles user settings."""
    
    def __init__(self):
        self.theme = None
        self.language = None
    
    def update_settings(self, theme, language):
        """Update user settings."""
        # ... settings logic
        return True
```

#### Configuration File (`merge_config.json`)

```json
{
  "base_class": "UserService",
  "source_classes": ["UserAuth", "UserProfile", "UserSettings"],
  "merge_methods": ["login", "update_profile", "update_settings"],
  "merge_props": ["username", "password", "email", "name", "theme", "language"]
}
```

**Note**: `merge_methods` and `merge_props` are optional. If not specified, ALL methods and properties from source classes will be merged.

#### Command

```bash
# Dry run (validate without changes)
code_refactor merge-classes -f user_services.py -c merge_config.json --dry-run

# Perform merge
code_refactor merge-classes -f user_services.py -c merge_config.json
```

#### Example: After

```python
class UserService:
    """Merged class combining functionality from multiple classes."""
    
    def __init__(self):
        self.username = None
        self.password = None
        self.email = None
        self.name = None
        self.theme = None
        self.language = None
    
    def login(self, username, password):
        """Authenticate user."""
        # ... login logic
        return True
    
    def update_profile(self, email, name):
        """Update user profile."""
        # ... profile logic
        return True
    
    def update_settings(self, theme, language):
        """Update user settings."""
        # ... settings logic
        return True
```

#### Safety Features

- **Pre-Operation Collection**: Collects all methods and properties from ALL source classes BEFORE merge
- **Strict Validation**: Compares pre-collected members with merged class to ensure completeness
- **Automatic Backup**: Creates backup before changes
- **Python Syntax Check**: Validates syntax after merging
- **Automatic Rollback**: Restores backup if validation fails

### Superclass Extraction

Extract common functionality from multiple classes into a base class.

#### Example: Before

```python
class Dog:
    """Represents a dog."""
    
    def __init__(self, name):
        self.name = name
        self.species = "Canis lupus"
        self.legs = 4
    
    def make_sound(self):
        return "Woof!"
    
    def move(self):
        return f"{self.name} is running"
    
    def eat(self, food):
        return f"{self.name} is eating {food}"

class Cat:
    """Represents a cat."""
    
    def __init__(self, name):
        self.name = name
        self.species = "Felis catus"
        self.legs = 4
    
    def make_sound(self):
        return "Meow!"
    
    def move(self):
        return f"{self.name} is walking"
    
    def eat(self, food):
        return f"{self.name} is eating {food}"
```

#### Configuration File (`extract_config.json`)

```json
{
  "base_class": "Animal",
  "child_classes": ["Dog", "Cat"],
  "abstract_methods": ["make_sound"],
  "extract_from": {
    "Dog": {
      "properties": ["name", "species", "legs"],
      "methods": ["move", "eat"]
    },
    "Cat": {
      "properties": ["name", "species", "legs"],
      "methods": ["move", "eat"]
    }
  }
}
```

#### Command

```bash
# Dry run (validate without changes)
code_refactor extract-superclass -f animals.py -c extract_config.json --dry-run

# Perform extraction
code_refactor extract-superclass -f animals.py -c extract_config.json
```

#### Example: After

```python
from abc import ABC, abstractmethod

class Animal(ABC):
    """Base class for extracted functionality."""
    
    def __init__(self):
        self.name = None
        self.species = None
        self.legs = None
    
    def move(self):
        return f"{self.name} is moving"
    
    def eat(self, food):
        return f"{self.name} is eating {food}"
    
    @abstractmethod
    def make_sound(self):
        pass

class Dog(Animal):
    """Represents a dog."""
    
    def __init__(self, name):
        super().__init__()
        self.name = name
        self.species = "Canis lupus"
        self.legs = 4
    
    def make_sound(self):
        return "Woof!"
    
    def move(self):
        return f"{self.name} is running"

class Cat(Animal):
    """Represents a cat."""
    
    def __init__(self, name):
        super().__init__()
        self.name = name
        self.species = "Felis catus"
        self.legs = 4
    
    def make_sound(self):
        return "Meow!"
    
    def move(self):
        return f"{self.name} is walking"
```

#### Safety Features

- **Multiple Inheritance Check**: Detects and prevents MRO conflicts
- **Method Compatibility**: Validates that methods have compatible signatures
- **Automatic Backup**: Creates backup before changes
- **Python Syntax Check**: Validates syntax after extraction
- **Completeness Check**: Ensures inheritance is correctly set up
- **Import Validation**: Verifies module can be imported
- **Automatic Rollback**: Restores backup if any validation fails

#### Configuration Format

```json
{
  "base_class": "BaseClassName",
  "child_classes": ["ChildClass1", "ChildClass2"],
  "abstract_methods": ["method1", "method2"],
  "extract_from": {
    "ChildClass1": {
      "properties": ["prop1", "prop2"],
      "methods": ["method1", "method2"]
    },
    "ChildClass2": {
      "properties": ["prop3"],
      "methods": ["method3"]
    }
  }
}
```

**Fields:**
- `base_class`: Name of the new base class to create
- `child_classes`: List of existing classes that will inherit from base class
- `abstract_methods`: List of method names that will be abstract in base class
- `extract_from`: Dictionary mapping child class names to their extracted elements
  - `properties`: List of property names to extract to base class
  - `methods`: List of method names to extract to base class

**Requirements:**
- All child classes must exist in the same file
- Methods with the same name must have compatible signatures across classes
- Child classes must not already have base classes (to avoid MRO conflicts)
- Base class name must not already exist

## Development

### Setup development environment

```bash
git clone https://github.com/vasilyvz/code-analysis-tool.git
cd code-analysis-tool
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### Running tests

```bash
pytest
```

**Tests that require the server:** Some integration tests expect the code-analysis server (and shared database) to be running; otherwise they are skipped (e.g. "Shared database not initialized", "RPC server unavailable"). To run those tests as well, start the server from the project root with the project venv activated:

```bash
python -m code_analysis.cli.server_manager_cli --config config.json start
```

Then run `pytest`. Use `restart` instead of `start` if the server is already running.

### Code formatting

```bash
black .
flake8 .
ruff check .  # configured Ruff scope
mypy .
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Run the linters and fix any issues
6. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Changelog

### 1.0.4
- **IMPROVED**: Strict completeness validation - pre-collects all methods and properties BEFORE operation, then validates they are all present after refactoring
- **NEW**: Class merging functionality - merge multiple classes into a single base class
- **NEW**: `merge-classes` CLI command for class merging operations
- Enhanced validation error messages with counts of original vs found members
- Improved documentation with examples for all refactoring operations

### 1.0.3
- Added SQLite database support for faster analysis
- Added class splitting refactoring functionality
- Added superclass extraction refactoring functionality
- Enhanced safety with automatic backups and validation
- Improved documentation

### 1.0.2
- Changed console command name from `code-analysis` to `code_mapper`
- Fixed .gitignore to properly track source code directory
- All code quality checks passed

### 1.0.1
- Package configuration improvements
- Enhanced documentation

### 1.0.0
- Initial release
- Basic code analysis functionality
- CLI interface
- YAML report generation
- Issue detection
