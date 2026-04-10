# Phase 21: Universal CLI Interface - Design

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Pharos CLI                              │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │   Commands   │  │   Formatters │  │   Config     │    │
│  │              │  │              │  │              │    │
│  │ - resource   │  │ - JSON       │  │ - Profiles   │    │
│  │ - search     │  │ - Table      │  │ - Auth       │    │
│  │ - collection │  │ - Tree       │  │ - Keyring    │    │
│  │ - annotate   │  │ - CSV        │  │              │    │
│  │ - graph      │  │ - Progress   │  │              │    │
│  │ - quality    │  │              │  │              │    │
│  │ - taxonomy   │  │              │  │              │    │
│  │ - recommend  │  │              │  │              │    │
│  │ - code       │  │              │  │              │    │
│  │ - ask        │  │              │  │              │    │
│  │ - health     │  │              │  │              │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              API Client Layer                       │  │
│  │  - HTTP client (httpx)                              │  │
│  │  - Authentication (JWT, OAuth2)                     │  │
│  │  - Error handling & retries                         │  │
│  │  - Response parsing                                 │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ HTTPS
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  Pharos Backend API                         │
│                                                             │
│  /api/v1/resources, /api/v1/search, /api/v1/collections   │
│  /api/v1/annotations, /api/v1/graph, /api/v1/quality      │
│  /api/v1/taxonomy, /api/v1/recommendations, /api/v1/code  │
│  /api/v1/rag, /api/v1/health                               │
└─────────────────────────────────────────────────────────────┘
```

## Technology Stack

### Core Framework
- **Click** or **Typer**: CLI framework (Typer preferred for type hints)
- **Rich**: Beautiful terminal output (tables, progress bars, colors)
- **httpx**: Async HTTP client for API calls
- **Pydantic**: Data validation and settings management

### Additional Libraries
- **keyring**: Secure credential storage
- **click-completion** or **typer-completion**: Shell completion
- **python-dotenv**: Environment variable loading
- **PyYAML**: Config file parsing
- **tabulate**: Table formatting (fallback)
- **tqdm**: Progress bars (fallback)

### Development Tools
- **pytest**: Testing framework
- **pytest-httpx**: Mock HTTP requests
- **black**: Code formatting
- **ruff**: Linting
- **mypy**: Type checking

## Project Structure

```
pharos-cli/
├── pyproject.toml              # Project metadata, dependencies
├── README.md                   # Installation and usage guide
├── LICENSE                     # MIT License
├── .gitignore
├── pharos_cli/
│   ├── __init__.py
│   ├── __main__.py             # Entry point: python -m pharos_cli
│   ├── cli.py                  # Main CLI app definition
│   ├── version.py              # Version string
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings.py         # Config management (Pydantic)
│   │   ├── profiles.py         # Profile switching
│   │   └── keyring_store.py    # Secure credential storage
│   │
│   ├── client/
│   │   ├── __init__.py
│   │   ├── api_client.py       # Base HTTP client
│   │   ├── auth.py             # Authentication logic
│   │   ├── exceptions.py       # Custom exceptions
│   │   └── models.py           # API response models
│   │
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── auth.py             # pharos auth
│   │   ├── resource.py         # pharos resource
│   │   ├── search.py           # pharos search
│   │   ├── collection.py       # pharos collection
│   │   ├── annotate.py         # pharos annotate
│   │   ├── graph.py            # pharos graph
│   │   ├── quality.py          # pharos quality
│   │   ├── taxonomy.py         # pharos taxonomy
│   │   ├── recommend.py        # pharos recommend
│   │   ├── code.py             # pharos code
│   │   ├── ask.py              # pharos ask (RAG)
│   │   ├── chat.py             # pharos chat (interactive)
│   │   ├── health.py           # pharos health
│   │   ├── backup.py           # pharos backup/restore
│   │   └── batch.py            # pharos batch
│   │
│   ├── formatters/
│   │   ├── __init__.py
│   │   ├── json_formatter.py   # JSON output
│   │   ├── table_formatter.py  # Table output (Rich)
│   │   ├── tree_formatter.py   # Tree output (Rich)
│   │   ├── csv_formatter.py    # CSV output
│   │   └── base.py             # Base formatter interface
│   │
│   └── utils/
│       ├── __init__.py
│       ├── console.py          # Rich console singleton
│       ├── progress.py         # Progress bar helpers
│       ├── validators.py       # Input validation
│       └── helpers.py          # Misc utilities
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # Pytest fixtures
│   ├── test_config.py
│   ├── test_client.py
│   ├── test_commands/
│   │   ├── test_resource.py
│   │   ├── test_search.py
│   │   └── ...
│   └── test_formatters.py
│
├── docs/
│   ├── installation.md
│   ├── configuration.md
│   ├── commands.md             # Command reference
│   ├── examples.md             # Usage examples
│   └── development.md          # Contributing guide
│
└── scripts/
    ├── install_completion.sh   # Shell completion installer
    └── release.sh              # Release automation
```

## Command Structure

### Naming Convention

**Pattern**: `pharos <noun> <verb> [arguments] [options]`

Examples:
- `pharos resource add file.py`
- `pharos search "machine learning" --hybrid`
- `pharos collection create "ML Papers"`
- `pharos graph citations 123`

### Command Groups

```python
# Main CLI app
@app.command()
def version():
    """Show Pharos CLI version."""
    pass

# Auth commands
@app.group()
def auth():
    """Authentication commands."""
    pass

@auth.command()
def login():
    """Login to Pharos."""
    pass

@auth.command()
def logout():
    """Logout from Pharos."""
    pass

@auth.command()
def whoami():
    """Show current user."""
    pass

# Resource commands
@app.group()
def resource():
    """Resource management commands."""
    pass

@resource.command()
def add(file: Path):
    """Add a resource."""
    pass

@resource.command()
def list(type: str = None):
    """List resources."""
    pass

@resource.command()
def get(id: int):
    """Get resource details."""
    pass

@resource.command()
def update(id: int, title: str = None):
    """Update resource metadata."""
    pass

@resource.command()
def delete(id: int):
    """Delete a resource."""
    pass

@resource.command()
def import_dir(path: Path, recursive: bool = False):
    """Import resources from directory."""
    pass

# Similar structure for other command groups...
```

## Configuration Management

### Config File Format (YAML)

```yaml
# ~/.pharos/config.yaml or ~/.config/pharos/config.yaml

# Active profile
active_profile: default

# Profiles
profiles:
  default:
    api_url: http://localhost:8000
    api_key: null  # Stored in keyring
    timeout: 30
    verify_ssl: true
    
  production:
    api_url: https://pharos.onrender.com
    api_key: null  # Stored in keyring
    timeout: 60
    verify_ssl: true
    
  local:
    api_url: http://localhost:8000
    api_key: null
    timeout: 10
    verify_ssl: false

# Output preferences
output:
  format: table  # json, table, tree, csv
  color: auto    # auto, always, never
  pager: auto    # auto, always, never
  
# Behavior
behavior:
  confirm_destructive: true
  show_progress: true
  parallel_batch: true
  max_workers: 4
```

### Environment Variables

```bash
# Override config values
PHAROS_API_URL=https://pharos.onrender.com
PHAROS_API_KEY=sk_live_...
PHAROS_PROFILE=production
PHAROS_OUTPUT_FORMAT=json
PHAROS_NO_COLOR=1
PHAROS_VERIFY_SSL=0
```

### Credential Storage

```python
# Use keyring for secure storage
import keyring

# Store API key
keyring.set_password("pharos-cli", "default", api_key)

# Retrieve API key
api_key = keyring.get_password("pharos-cli", "default")

# Delete API key
keyring.delete_password("pharos-cli", "default")
```

## API Client Design

### Base Client

```python
from typing import Optional, Dict, Any
import httpx
from pydantic import BaseModel

class APIClient:
    """Base HTTP client for Pharos API."""
    
    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        timeout: int = 30,
        verify_ssl: bool = True
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            verify=verify_ssl,
            headers=self._get_headers()
        )
    
    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "User-Agent": f"pharos-cli/{__version__}",
            "Accept": "application/json"
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers
    
    def request(
        self,
        method: str,
        endpoint: str,
        **kwargs
    ) -> httpx.Response:
        """Make HTTP request with error handling."""
        try:
            response = self._client.request(method, endpoint, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            raise APIError.from_response(e.response)
        except httpx.RequestError as e:
            raise NetworkError(str(e))
    
    def get(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        response = self.request("GET", endpoint, **kwargs)
        return response.json()
    
    def post(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        response = self.request("POST", endpoint, **kwargs)
        return response.json()
    
    def put(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        response = self.request("PUT", endpoint, **kwargs)
        return response.json()
    
    def delete(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        response = self.request("DELETE", endpoint, **kwargs)
        return response.json()
```

### Resource-Specific Clients

```python
class ResourceClient:
    """Client for resource operations."""
    
    def __init__(self, api_client: APIClient):
        self.api = api_client
    
    def create(self, title: str, content: str, **kwargs) -> Dict:
        return self.api.post("/api/v1/resources", json={
            "title": title,
            "content": content,
            **kwargs
        })
    
    def list(self, skip: int = 0, limit: int = 100, **filters) -> Dict:
        params = {"skip": skip, "limit": limit, **filters}
        return self.api.get("/api/v1/resources", params=params)
    
    def get(self, resource_id: int) -> Dict:
        return self.api.get(f"/api/v1/resources/{resource_id}")
    
    def update(self, resource_id: int, **updates) -> Dict:
        return self.api.put(f"/api/v1/resources/{resource_id}", json=updates)
    
    def delete(self, resource_id: int) -> None:
        self.api.delete(f"/api/v1/resources/{resource_id}")

# Similar clients for search, collections, annotations, etc.
```

## Output Formatting

### Formatter Interface

```python
from abc import ABC, abstractmethod
from typing import Any, List, Dict

class Formatter(ABC):
    """Base formatter interface."""
    
    @abstractmethod
    def format(self, data: Any) -> str:
        """Format data for output."""
        pass
    
    @abstractmethod
    def format_list(self, items: List[Dict]) -> str:
        """Format list of items."""
        pass
    
    @abstractmethod
    def format_error(self, error: Exception) -> str:
        """Format error message."""
        pass
```

### JSON Formatter

```python
import json

class JSONFormatter(Formatter):
    """JSON output formatter."""
    
    def __init__(self, indent: int = 2):
        self.indent = indent
    
    def format(self, data: Any) -> str:
        return json.dumps(data, indent=self.indent, default=str)
    
    def format_list(self, items: List[Dict]) -> str:
        return self.format(items)
    
    def format_error(self, error: Exception) -> str:
        return json.dumps({
            "error": str(error),
            "type": type(error).__name__
        }, indent=self.indent)
```

### Table Formatter (Rich)

```python
from rich.table import Table
from rich.console import Console

class TableFormatter(Formatter):
    """Table output formatter using Rich."""
    
    def __init__(self, console: Console):
        self.console = console
    
    def format_list(self, items: List[Dict]) -> str:
        if not items:
            return "No results found."
        
        # Create table
        table = Table(show_header=True, header_style="bold magenta")
        
        # Add columns from first item
        for key in items[0].keys():
            table.add_column(key.replace("_", " ").title())
        
        # Add rows
        for item in items:
            table.add_row(*[str(v) for v in item.values()])
        
        # Render to string
        with self.console.capture() as capture:
            self.console.print(table)
        
        return capture.get()
```

### Tree Formatter (Rich)

```python
from rich.tree import Tree

class TreeFormatter(Formatter):
    """Tree output formatter for hierarchical data."""
    
    def format(self, data: Dict, label: str = "Root") -> str:
        tree = Tree(label)
        self._build_tree(tree, data)
        
        with self.console.capture() as capture:
            self.console.print(tree)
        
        return capture.get()
    
    def _build_tree(self, tree: Tree, data: Any):
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    branch = tree.add(f"[bold]{key}[/bold]")
                    self._build_tree(branch, value)
                else:
                    tree.add(f"{key}: {value}")
        elif isinstance(data, list):
            for i, item in enumerate(data):
                branch = tree.add(f"[{i}]")
                self._build_tree(branch, item)
```

## Progress Indicators

### Progress Bar

```python
from rich.progress import Progress, SpinnerColumn, TextColumn

def with_progress(items: List, description: str):
    """Iterate with progress bar."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True
    ) as progress:
        task = progress.add_task(description, total=len(items))
        for item in items:
            yield item
            progress.update(task, advance=1)
```

### Spinner

```python
from rich.spinner import Spinner
from rich.live import Live

def with_spinner(message: str):
    """Context manager for spinner."""
    spinner = Spinner("dots", text=message)
    return Live(spinner, transient=True)

# Usage
with with_spinner("Analyzing code..."):
    result = analyze_code(file)
```

## Error Handling

### Custom Exceptions

```python
class PharosError(Exception):
    """Base exception for Pharos CLI."""
    pass

class APIError(PharosError):
    """API request failed."""
    
    def __init__(self, status_code: int, message: str, details: Dict = None):
        self.status_code = status_code
        self.message = message
        self.details = details or {}
        super().__init__(f"API Error {status_code}: {message}")
    
    @classmethod
    def from_response(cls, response: httpx.Response):
        try:
            data = response.json()
            message = data.get("detail", response.text)
            details = data
        except:
            message = response.text
            details = {}
        
        return cls(response.status_code, message, details)

class NetworkError(PharosError):
    """Network connection failed."""
    pass

class ConfigError(PharosError):
    """Configuration error."""
    pass

class AuthenticationError(PharosError):
    """Authentication failed."""
    pass
```

### Error Display

```python
from rich.panel import Panel

def display_error(error: Exception, verbose: bool = False):
    """Display error with Rich formatting."""
    console = get_console()
    
    if isinstance(error, APIError):
        panel = Panel(
            f"[red]{error.message}[/red]\n\n"
            f"Status Code: {error.status_code}",
            title="API Error",
            border_style="red"
        )
        console.print(panel)
        
        if verbose and error.details:
            console.print("\n[dim]Details:[/dim]")
            console.print_json(data=error.details)
    
    elif isinstance(error, NetworkError):
        console.print(f"[red]Network Error:[/red] {error}")
        console.print("[dim]Check your internet connection and API URL.[/dim]")
    
    else:
        console.print(f"[red]Error:[/red] {error}")
```

## Shell Completion

### Bash Completion

```bash
# ~/.bashrc or ~/.bash_profile
eval "$(_PHAROS_COMPLETE=bash_source pharos)"
```

### Zsh Completion

```zsh
# ~/.zshrc
eval "$(_PHAROS_COMPLETE=zsh_source pharos)"
```

### Fish Completion

```fish
# ~/.config/fish/completions/pharos.fish
_PHAROS_COMPLETE=fish_source pharos | source
```

### Implementation (Typer)

```python
import typer
from typer.completion import install_callback

app = typer.Typer()

@app.command()
def completion(
    shell: str = typer.Argument(None, help="Shell type: bash, zsh, fish")
):
    """Generate shell completion script."""
    if shell:
        install_callback(shell)
    else:
        typer.echo("Please specify shell: bash, zsh, or fish")
```

## Testing Strategy

### Unit Tests

```python
import pytest
from pharos_cli.client import APIClient
from pharos_cli.commands.resource import ResourceClient

def test_resource_create(mock_api_client):
    """Test resource creation."""
    client = ResourceClient(mock_api_client)
    
    result = client.create(
        title="Test Resource",
        content="Test content"
    )
    
    assert result["title"] == "Test Resource"
    assert "id" in result

def test_resource_list_with_filters(mock_api_client):
    """Test resource listing with filters."""
    client = ResourceClient(mock_api_client)
    
    result = client.list(
        resource_type="code",
        language="python"
    )
    
    assert len(result["items"]) > 0
    assert all(r["resource_type"] == "code" for r in result["items"])
```

### Integration Tests

```python
import pytest
from typer.testing import CliRunner
from pharos_cli.cli import app

runner = CliRunner()

def test_resource_add_command():
    """Test resource add command."""
    result = runner.invoke(app, [
        "resource", "add", "test.py",
        "--title", "Test File"
    ])
    
    assert result.exit_code == 0
    assert "Resource created" in result.stdout

def test_search_command():
    """Test search command."""
    result = runner.invoke(app, [
        "search", "machine learning",
        "--format", "json"
    ])
    
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "results" in data
```

### Mock API Responses

```python
import pytest
from pytest_httpx import HTTPXMock

@pytest.fixture
def mock_api_client(httpx_mock: HTTPXMock):
    """Mock API client for testing."""
    
    # Mock resource creation
    httpx_mock.add_response(
        method="POST",
        url="http://localhost:8000/api/v1/resources",
        json={"id": 1, "title": "Test Resource"}
    )
    
    # Mock resource listing
    httpx_mock.add_response(
        method="GET",
        url="http://localhost:8000/api/v1/resources",
        json={"items": [], "total": 0}
    )
    
    return APIClient("http://localhost:8000")
```

## Deployment & Distribution

### PyPI Package

```toml
# pyproject.toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "pharos-cli"
version = "0.1.0"
description = "Command-line interface for Pharos knowledge management system"
authors = [{name = "Pharos Team"}]
license = {text = "MIT"}
readme = "README.md"
requires-python = ">=3.8"
dependencies = [
    "typer[all]>=0.9.0",
    "rich>=13.0.0",
    "httpx>=0.24.0",
    "pydantic>=2.0.0",
    "pyyaml>=6.0",
    "keyring>=24.0.0",
    "python-dotenv>=1.0.0"
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-httpx>=0.22.0",
    "pytest-cov>=4.0.0",
    "black>=23.0.0",
    "ruff>=0.1.0",
    "mypy>=1.0.0"
]

[project.scripts]
pharos = "pharos_cli.cli:app"

[project.urls]
Homepage = "https://github.com/yourusername/pharos"
Documentation = "https://pharos.readthedocs.io"
Repository = "https://github.com/yourusername/pharos-cli"
```

### Installation Methods

```bash
# From PyPI
pip install pharos-cli

# From PyPI with pipx (isolated)
pipx install pharos-cli

# From source
git clone https://github.com/yourusername/pharos-cli
cd pharos-cli
pip install -e .

# From GitHub directly
pip install git+https://github.com/yourusername/pharos-cli
```

## Security Considerations

### Credential Storage
- Use keyring for secure storage
- Never log API keys
- Clear credentials on logout
- Support credential rotation

### API Communication
- Always use HTTPS in production
- Verify SSL certificates by default
- Support custom CA certificates
- Timeout all requests

### Input Validation
- Validate all user inputs
- Sanitize file paths
- Prevent command injection
- Limit file sizes

## Performance Optimization

### Caching
- Cache API responses (short TTL)
- Cache config file parsing
- Cache shell completion data

### Parallel Execution
- Use asyncio for concurrent API calls
- Thread pool for batch operations
- Progress tracking for parallel tasks

### Streaming
- Stream large file uploads
- Stream search results
- Stream batch operation results

## Related Documentation

- [Requirements](requirements.md)
- [Tasks](tasks.md)
- [API Documentation](../../../backend/docs/api/overview.md)
- [Tech Stack](../../../.kiro/steering/tech.md)
