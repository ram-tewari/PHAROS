# MCP Integration Guide

How to integrate with the Model Context Protocol (MCP) server in Pharos.

> **Phase**: 20 - Frontend-Backend Infrastructure Support
> **Status**: Complete

## Overview

The MCP (Model Context Protocol) server provides a standardized interface for AI agents and tools to interact with Pharos's capabilities. It exposes backend features as MCP tools with schema validation, authentication, rate limiting, and session management.

## Features

### 1. Tool Registry

Centralized registry of available tools:

- **Schema Validation**: JSON Schema validation for tool inputs
- **Dynamic Registration**: Register new tools at runtime
- **Tool Discovery**: List all available tools with schemas
- **Type Safety**: Strongly typed tool definitions

### 2. Session Management

Stateful sessions for context preservation:

- **Session Context**: Maintain conversation history
- **Tool Invocations**: Track tool usage per session
- **Session Lifecycle**: Create, use, and close sessions
- **Context Preservation**: Maintain state across multiple tool calls

### 3. Security

Enterprise-grade security features:

- **JWT Authentication**: Token-based authentication
- **Rate Limiting**: Per-user and per-tool rate limits
- **Input Validation**: Schema-based validation
- **Audit Logging**: Track all tool invocations

### 4. Available Tools

Pharos capabilities exposed as MCP tools:

- `search_resources`: Search knowledge base
- `get_hover_info`: Get code hover information
- `compute_graph_metrics`: Compute centrality metrics
- `detect_communities`: Detect graph communities
- `generate_plan`: Generate multi-step plans
- `parse_architecture`: Parse architecture documents
- `link_pdf_to_code`: Auto-link PDFs to code

## API Reference

### GET `/mcp/tools`

List all available MCP tools.

**Response**:
```json
{
  "tools": [
    {
      "name": "search_resources",
      "description": "Search the knowledge base using hybrid search",
      "input_schema": {
        "type": "object",
        "properties": {
          "query": {
            "type": "string",
            "description": "Search query"
          },
          "limit": {
            "type": "integer",
            "default": 10,
            "description": "Maximum number of results"
          }
        },
        "required": ["query"]
      },
      "output_schema": {
        "type": "object",
        "properties": {
          "results": {
            "type": "array",
            "items": {
              "type": "object"
            }
          }
        }
      }
    }
  ]
}
```

### POST `/mcp/invoke`

Invoke an MCP tool.

**Request Body**:
```json
{
  "tool_name": "search_resources",
  "arguments": {
    "query": "machine learning",
    "limit": 5
  },
  "session_id": "uuid-session-1"
}
```

**Response**:
```json
{
  "tool_name": "search_resources",
  "result": {
    "results": [
      {
        "id": "uuid-1",
        "title": "Introduction to Machine Learning",
        "score": 0.95
      }
    ]
  },
  "execution_time": 0.15,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### POST `/mcp/sessions`

Create a new MCP session.

**Request Body**:
```json
{
  "context": {
    "user_id": "uuid-user-1",
    "preferences": {
      "language": "en",
      "max_results": 10
    }
  }
}
```

**Response**:
```json
{
  "session_id": "uuid-session-1",
  "created_at": "2024-01-15T10:30:00Z",
  "expires_at": "2024-01-15T11:30:00Z"
}
```

### DELETE `/mcp/sessions/{session_id}`

Close an MCP session.

**Response**:
```json
{
  "session_id": "uuid-session-1",
  "closed_at": "2024-01-15T10:45:00Z",
  "total_invocations": 15
}
```

## Usage Examples

### Python Client

```python
import requests

class MCPClient:
    def __init__(self, base_url, token):
        self.base_url = base_url
        self.token = token
        self.session_id = None
    
    def create_session(self, context=None):
        """Create a new MCP session."""
        response = requests.post(
            f"{self.base_url}/mcp/sessions",
            json={"context": context or {}},
            headers={"Authorization": f"Bearer {self.token}"}
        )
        session = response.json()
        self.session_id = session['session_id']
        return session
    
    def list_tools(self):
        """List all available tools."""
        response = requests.get(
            f"{self.base_url}/mcp/tools",
            headers={"Authorization": f"Bearer {self.token}"}
        )
        return response.json()['tools']
    
    def invoke_tool(self, tool_name, arguments):
        """Invoke an MCP tool."""
        response = requests.post(
            f"{self.base_url}/mcp/invoke",
            json={
                "tool_name": tool_name,
                "arguments": arguments,
                "session_id": self.session_id
            },
            headers={"Authorization": f"Bearer {self.token}"}
        )
        return response.json()
    
    def close_session(self):
        """Close the current session."""
        if self.session_id:
            response = requests.delete(
                f"{self.base_url}/mcp/sessions/{self.session_id}",
                headers={"Authorization": f"Bearer {self.token}"}
            )
            return response.json()

# Usage
client = MCPClient("http://localhost:8000", "your-token")

# Create session
session = client.create_session({"user_id": "uuid-user-1"})

# List available tools
tools = client.list_tools()
print(f"Available tools: {[t['name'] for t in tools]}")

# Invoke tool
result = client.invoke_tool(
    "search_resources",
    {"query": "machine learning", "limit": 5}
)
print(f"Found {len(result['result']['results'])} results")

# Close session
client.close_session()
```

### JavaScript/TypeScript Client

```typescript
interface MCPTool {
  name: string;
  description: string;
  input_schema: any;
  output_schema: any;
}

interface MCPSession {
  session_id: string;
  created_at: string;
  expires_at: string;
}

interface MCPInvocation {
  tool_name: string;
  result: any;
  execution_time: number;
  timestamp: string;
}

class MCPClient {
  private baseUrl: string;
  private token: string;
  private sessionId: string | null = null;
  
  constructor(baseUrl: string, token: string) {
    this.baseUrl = baseUrl;
    this.token = token;
  }
  
  async createSession(context?: any): Promise<MCPSession> {
    const response = await fetch(`${this.baseUrl}/mcp/sessions`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ context: context || {} })
    });
    
    const session = await response.json();
    this.sessionId = session.session_id;
    return session;
  }
  
  async listTools(): Promise<MCPTool[]> {
    const response = await fetch(`${this.baseUrl}/mcp/tools`, {
      headers: {
        'Authorization': `Bearer ${this.token}`
      }
    });
    
    const data = await response.json();
    return data.tools;
  }
  
  async invokeTool(toolName: string, arguments: any): Promise<MCPInvocation> {
    const response = await fetch(`${this.baseUrl}/mcp/invoke`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        tool_name: toolName,
        arguments: arguments,
        session_id: this.sessionId
      })
    });
    
    return response.json();
  }
  
  async closeSession(): Promise<any> {
    if (!this.sessionId) {
      throw new Error('No active session');
    }
    
    const response = await fetch(
      `${this.baseUrl}/mcp/sessions/${this.sessionId}`,
      {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${this.token}`
        }
      }
    );
    
    return response.json();
  }
}

// Usage
const client = new MCPClient('http://localhost:8000', 'your-token');

// Create session
const session = await client.createSession({ user_id: 'uuid-user-1' });

// List tools
const tools = await client.listTools();
console.log(`Available tools: ${tools.map(t => t.name).join(', ')}`);

// Invoke tool
const result = await client.invokeTool('search_resources', {
  query: 'machine learning',
  limit: 5
});
console.log(`Found ${result.result.results.length} results`);

// Close session
await client.closeSession();
```

## Available Tools

### 1. search_resources

Search the knowledge base using hybrid search.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "description": "Search query"
    },
    "limit": {
      "type": "integer",
      "default": 10,
      "description": "Maximum number of results"
    },
    "filters": {
      "type": "object",
      "description": "Optional filters"
    }
  },
  "required": ["query"]
}
```

**Example**:
```python
result = client.invoke_tool("search_resources", {
    "query": "neural networks",
    "limit": 5,
    "filters": {"type": "paper"}
})
```

### 2. get_hover_info

Get hover information for code symbols.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "file_path": {
      "type": "string",
      "description": "Relative file path"
    },
    "line": {
      "type": "integer",
      "description": "Line number (1-indexed)"
    },
    "column": {
      "type": "integer",
      "description": "Column number (0-indexed)"
    },
    "resource_id": {
      "type": "string",
      "format": "uuid",
      "description": "Repository resource ID"
    }
  },
  "required": ["file_path", "line", "column", "resource_id"]
}
```

**Example**:
```python
result = client.invoke_tool("get_hover_info", {
    "file_path": "src/model.py",
    "line": 50,
    "column": 10,
    "resource_id": "uuid-repo-1"
})
```

### 3. compute_graph_metrics

Compute centrality metrics for graph nodes.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "resource_ids": {
      "type": "array",
      "items": {"type": "string", "format": "uuid"},
      "description": "Resources to compute metrics for"
    },
    "metric_types": {
      "type": "array",
      "items": {"type": "string", "enum": ["degree", "betweenness", "pagerank"]},
      "description": "Metrics to compute"
    }
  }
}
```

**Example**:
```python
result = client.invoke_tool("compute_graph_metrics", {
    "resource_ids": ["uuid-1", "uuid-2"],
    "metric_types": ["degree", "pagerank"]
})
```

### 4. detect_communities

Detect communities in the knowledge graph.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "resource_ids": {
      "type": "array",
      "items": {"type": "string", "format": "uuid"},
      "description": "Resources to analyze"
    },
    "resolution": {
      "type": "number",
      "default": 1.0,
      "description": "Community detection resolution"
    }
  }
}
```

**Example**:
```python
result = client.invoke_tool("detect_communities", {
    "resolution": 1.0
})
```

### 5. generate_plan

Generate a multi-step plan for a task.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "task_description": {
      "type": "string",
      "description": "Task to plan"
    },
    "context": {
      "type": "object",
      "description": "Planning context"
    },
    "max_steps": {
      "type": "integer",
      "default": 10,
      "description": "Maximum number of steps"
    }
  },
  "required": ["task_description"]
}
```

**Example**:
```python
result = client.invoke_tool("generate_plan", {
    "task_description": "Implement user authentication",
    "context": {"existing_features": ["database", "API"]},
    "max_steps": 10
})
```

### 6. parse_architecture

Parse an architecture document.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "resource_id": {
      "type": "string",
      "format": "uuid",
      "description": "Architecture document resource ID"
    },
    "compare_with_repo": {
      "type": "boolean",
      "default": false,
      "description": "Compare with actual codebase"
    },
    "repo_resource_id": {
      "type": "string",
      "format": "uuid",
      "description": "Repository resource ID"
    }
  },
  "required": ["resource_id"]
}
```

**Example**:
```python
result = client.invoke_tool("parse_architecture", {
    "resource_id": "uuid-doc-1",
    "compare_with_repo": True,
    "repo_resource_id": "uuid-repo-1"
})
```

### 7. link_pdf_to_code

Auto-link PDF documents to code repositories.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "pdf_resource_id": {
      "type": "string",
      "format": "uuid",
      "description": "PDF resource ID"
    },
    "code_resource_id": {
      "type": "string",
      "format": "uuid",
      "description": "Code repository resource ID"
    },
    "similarity_threshold": {
      "type": "number",
      "default": 0.7,
      "description": "Minimum similarity for linking"
    }
  },
  "required": ["pdf_resource_id", "code_resource_id"]
}
```

**Example**:
```python
result = client.invoke_tool("link_pdf_to_code", {
    "pdf_resource_id": "uuid-pdf-1",
    "code_resource_id": "uuid-repo-1",
    "similarity_threshold": 0.7
})
```

## Session Management

### Creating Sessions

Sessions maintain context across multiple tool invocations:

```python
# Create session with context
session = client.create_session({
    "user_id": "uuid-user-1",
    "preferences": {
        "language": "en",
        "max_results": 10
    },
    "workspace": {
        "active_repo": "uuid-repo-1",
        "active_document": "uuid-doc-1"
    }
})

# Session ID is automatically used for subsequent invocations
result1 = client.invoke_tool("search_resources", {"query": "ML"})
result2 = client.invoke_tool("get_hover_info", {...})
```

### Session Expiration

Sessions expire after 1 hour of inactivity:

```python
# Check session expiration
session = client.create_session()
print(f"Session expires at: {session['expires_at']}")

# Extend session by making invocations
client.invoke_tool("search_resources", {"query": "test"})
```

### Closing Sessions

Always close sessions when done:

```python
try:
    session = client.create_session()
    # Use session...
finally:
    client.close_session()
```

## Security

### Authentication

All MCP endpoints require JWT authentication:

```python
# Get token from authentication endpoint
response = requests.post(
    "http://localhost:8000/auth/token",
    data={"username": "user", "password": "pass"}
)
token = response.json()['access_token']

# Use token with MCP client
client = MCPClient("http://localhost:8000", token)
```

### Rate Limiting

Rate limits apply per user and per tool:

| User Tier | Requests/Minute | Requests/Hour |
|-----------|----------------|---------------|
| Free | 10 | 100 |
| Premium | 100 | 1000 |
| Admin | Unlimited | Unlimited |

**Handling Rate Limits**:

```python
try:
    result = client.invoke_tool("search_resources", {"query": "test"})
except requests.exceptions.HTTPError as e:
    if e.response.status_code == 429:
        retry_after = e.response.headers.get('Retry-After')
        print(f"Rate limited. Retry after {retry_after} seconds")
```

### Input Validation

All tool inputs are validated against JSON schemas:

```python
# Invalid input
try:
    result = client.invoke_tool("search_resources", {
        "query": 123  # Should be string
    })
except requests.exceptions.HTTPError as e:
    if e.response.status_code == 422:
        errors = e.response.json()['detail']
        print(f"Validation errors: {errors}")
```

## Integration Examples

### AI Agent Integration

```python
class AIAgent:
    def __init__(self, mcp_client):
        self.mcp = mcp_client
        self.session = None
    
    async def start(self):
        """Start agent session."""
        self.session = self.mcp.create_session({
            "agent_id": "ai-agent-1",
            "capabilities": ["search", "analyze", "plan"]
        })
    
    async def search_and_analyze(self, query):
        """Search and analyze results."""
        # Search
        search_result = self.mcp.invoke_tool("search_resources", {
            "query": query,
            "limit": 10
        })
        
        # Analyze top result
        if search_result['result']['results']:
            top_result = search_result['result']['results'][0]
            
            # Get graph metrics
            metrics = self.mcp.invoke_tool("compute_graph_metrics", {
                "resource_ids": [top_result['id']],
                "metric_types": ["pagerank", "degree"]
            })
            
            return {
                "search_results": search_result['result'],
                "metrics": metrics['result']
            }
    
    async def plan_task(self, task_description):
        """Generate plan for task."""
        plan = self.mcp.invoke_tool("generate_plan", {
            "task_description": task_description,
            "context": {"agent_id": "ai-agent-1"}
        })
        
        return plan['result']
    
    async def stop(self):
        """Stop agent session."""
        self.mcp.close_session()
```

### IDE Extension Integration

```typescript
class IDEExtension {
  private mcp: MCPClient;
  
  constructor(baseUrl: string, token: string) {
    this.mcp = new MCPClient(baseUrl, token);
  }
  
  async initialize() {
    await this.mcp.createSession({
      ide: 'vscode',
      workspace: vscode.workspace.rootPath
    });
  }
  
  async provideHover(document: vscode.TextDocument, position: vscode.Position) {
    const filePath = vscode.workspace.asRelativePath(document.uri);
    const line = position.line + 1;
    const column = position.character;
    
    const result = await this.mcp.invokeTool('get_hover_info', {
      file_path: filePath,
      line: line,
      column: column,
      resource_id: this.getActiveRepoId()
    });
    
    return new vscode.Hover(result.result.symbol_info.description);
  }
  
  async searchWorkspace(query: string) {
    const result = await this.mcp.invokeTool('search_resources', {
      query: query,
      limit: 20
    });
    
    return result.result.results;
  }
  
  async dispose() {
    await this.mcp.closeSession();
  }
}
```

## Best Practices

### 1. Session Management

Always use sessions for related operations:

```python
# Good: Use session
with MCPClient(url, token) as client:
    client.create_session()
    result1 = client.invoke_tool("search_resources", {...})
    result2 = client.invoke_tool("get_hover_info", {...})
    client.close_session()

# Bad: No session
client = MCPClient(url, token)
result1 = client.invoke_tool("search_resources", {...})  # No context
result2 = client.invoke_tool("get_hover_info", {...})  # No context
```

### 2. Error Handling

Handle all error cases:

```python
try:
    result = client.invoke_tool("search_resources", {"query": "test"})
except requests.exceptions.HTTPError as e:
    if e.response.status_code == 401:
        print("Authentication failed")
    elif e.response.status_code == 422:
        print("Invalid input")
    elif e.response.status_code == 429:
        print("Rate limited")
    else:
        print(f"Error: {e}")
```

### 3. Tool Discovery

Discover tools dynamically:

```python
# List available tools
tools = client.list_tools()

# Find tool by name
search_tool = next(t for t in tools if t['name'] == 'search_resources')

# Validate input against schema
from jsonschema import validate
validate({"query": "test"}, search_tool['input_schema'])
```

### 4. Rate Limit Management

Implement backoff strategy:

```python
import time

def invoke_with_retry(client, tool_name, arguments, max_retries=3):
    for attempt in range(max_retries):
        try:
            return client.invoke_tool(tool_name, arguments)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                retry_after = int(e.response.headers.get('Retry-After', 60))
                time.sleep(retry_after)
            else:
                raise
    raise Exception("Max retries exceeded")
```

## Troubleshooting

### Authentication Errors

**Problem**: 401 Unauthorized

**Solutions**:
1. Verify token is valid
2. Check token expiration
3. Ensure token has required permissions
4. Refresh token if expired

### Validation Errors

**Problem**: 422 Unprocessable Entity

**Solutions**:
1. Check input against tool schema
2. Verify required fields are present
3. Ensure correct data types
4. Review validation error details

### Rate Limit Errors

**Problem**: 429 Too Many Requests

**Solutions**:
1. Implement exponential backoff
2. Check rate limit headers
3. Upgrade to higher tier
4. Batch requests when possible

## Related Documentation

- [API Reference - MCP](../api/mcp.md) - Complete API documentation
- [Architecture - Phase 20](../architecture/phase20-features.md) - Architecture details
- [AI Planning Guide](ai-planning.md) - Planning features
- [Code Intelligence Guide](code-intelligence.md) - Code features

## Next Steps

1. **Build AI Agent**: Create intelligent agents using MCP tools
2. **Integrate with IDE**: Build IDE extensions
3. **Automate Workflows**: Use MCP for automation
4. **Explore Tools**: Try all available MCP tools
