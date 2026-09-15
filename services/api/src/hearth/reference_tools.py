"""Small, non-mutating reference MCP provider. No filesystem or network tools."""
from datetime import UTC, datetime
from typing import Literal

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings


def create_app():
    server = MCPServer('hearth reference tools', version='1.0.0', log_level='WARNING')

    @server.tool(structured_output=True)
    def calculate(operation: Literal['add', 'subtract', 'multiply', 'divide'], a: float, b: float) -> dict[str, object]:
        """Calculate with two numbers. This tool does not change anything."""
        import math

        from mcp.server.mcpserver.exceptions import ToolError
        if not math.isfinite(a) or not math.isfinite(b) or abs(a) > 1e100 or abs(b) > 1e100 or operation == 'divide' and b == 0:
            raise ToolError('Use finite numbers within 1e100, and a nonzero divisor.')
        result = {'add': lambda: a+b, 'subtract': lambda: a-b, 'multiply': lambda: a*b, 'divide': lambda: a/b}[operation]()
        return {'operation': operation, 'a': a, 'b': b, 'result': result}

    @server.tool(structured_output=True)
    def current_time() -> dict[str, object]:
        """Read the tool machine's current UTC date and time."""
        return {'utc': datetime.now(UTC).isoformat()}

    return server.streamable_http_app(stateless_http=True, json_response=True,
        transport_security=TransportSecuritySettings(allowed_hosts=['127.0.0.1:*', 'localhost:*', 'reference-tools:8096']))
