import os
import importlib
from typing import Dict
from fastapi import FastAPI, Request, Depends
from starlette.responses import Response
from app.core.logger import logger
from app.mcp.base import BaseMCPServer
from app.mcp.security import verify_mcp_auth
from mcp.server.sse import SseServerTransport

class MCPManager:
    """
    MCP 服务管理器。
    负责从 app/mcp/servers 目录自动加载所有服务并挂载到 FastAPI。
    由于 mcp.server.fastapi 在当前版本不可用，我们手动实现 SSE 挂载。
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MCPManager, cls).__new__(cls)
            cls._instance.servers: Dict[str, BaseMCPServer] = {}
        return cls._instance

    def load_servers(self):
        """
        扫描 servers 目录并加载所有有效的 MCP 服务。
        """
        base_path = os.path.join(os.path.dirname(__file__), "servers")
        if not os.path.exists(base_path):
            return

        for folder in os.listdir(base_path):
            folder_path = os.path.join(base_path, folder)
            if os.path.isdir(folder_path) and not folder.startswith("__"):
                try:
                    module = importlib.import_module(f"app.mcp.servers.{folder}.server")
                    if hasattr(module, "server") and isinstance(module.server, BaseMCPServer):
                        self.servers[folder] = module.server
                        logger.info(f"Loaded MCP Server: {folder}")
                except Exception as e:
                    logger.error(f"Failed to load MCP Server {folder}: {str(e)}")

    def mount_to_app(self, app: FastAPI, prefix: str = "/mcp"):
        """
        将加载的服务挂载到 FastAPI 路由。
        """
        for name, mcp_server in self.servers.items():
            # 创建 SSE 传输
            # 注意：endpoint 是处理 POST 消息的路径
            sse = SseServerTransport(f"{prefix}/{name}/messages")
            
            # 挂载 SSE 连接端点
            @app.get(f"{prefix}/{name}/sse")
            async def handle_sse(request: Request, _ = Depends(verify_mcp_auth)):
                async with sse.connect_sse(
                    request.scope, request.receive, request._send
                ) as streams:
                    await mcp_server.server.run(
                        streams[0], 
                        streams[1], 
                        mcp_server.server.create_initialization_options()
                    )
                return Response()

            # 挂载消息处理端点
            @app.post(f"{prefix}/{name}/messages")
            async def handle_messages(request: Request, _ = Depends(verify_mcp_auth)):
                await sse.handle_post_message(request.scope, request.receive, request._send)
            
            logger.info(f"Mounted MCP Server {name} (SSE) at {prefix}/{name}/sse")

mcp_manager = MCPManager()
