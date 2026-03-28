from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel
from mcp.server import Server
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource

class BaseMCPServer(ABC):
    """
    MCP 服务基类。
    所有业务 MCP 服务都应继承此类。
    """
    
    def __init__(self, name: str, version: str = "1.0.0"):
        self.name = name
        self.version = version
        self.server = Server(name)
        self._tools: Dict[str, Callable] = {}
        self._setup_handlers()

    @abstractmethod
    def _setup_handlers(self):
        """设置 MCP 协议处理器 (tools, resources, etc.)"""
        pass

    def register_tool(self, name: str, description: str, input_schema: type[BaseModel]):
        """
        装饰器或方法，用于注册工具。
        """
        def decorator(func: Callable):
            self._tools[name] = func
            
            @self.server.list_tools()
            async def handle_list_tools() -> List[Tool]:
                return [
                    Tool(
                        name=n,
                        description=d,
                        inputSchema=s.model_json_schema()
                    ) for n, (f, d, s) in self._get_tool_info().items()
                ]
            
            return func
        return decorator

    def _get_tool_info(self):
        # 这是一个内部辅助方法，实际实现中需要更精细的状态管理
        return {}
