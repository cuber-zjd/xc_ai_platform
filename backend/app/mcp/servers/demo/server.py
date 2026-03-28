from pydantic import BaseModel, Field
from app.mcp.base import BaseMCPServer
from mcp.types import Tool, TextContent

class EchoSchema(BaseModel):
    message: str = Field(..., description="The message to echo back")

class DemoServer(BaseMCPServer):
    def __init__(self):
        super().__init__(name="demo-server")

    def _setup_handlers(self):
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict | None) -> list[TextContent]:
            if name == "echo":
                msg = EchoSchema(**(arguments or {})).message
                return [TextContent(type="text", text=f"Echo: {msg}")]
            raise ValueError(f"Unknown tool: {name}")

        @self.server.list_tools()
        async def handle_list_tools() -> list[Tool]:
            return [
                Tool(
                    name="echo",
                    description="Returns the input message",
                    inputSchema=EchoSchema.model_json_schema()
                )
            ]

server = DemoServer()
