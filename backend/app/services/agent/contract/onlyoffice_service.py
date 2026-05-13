"""
OnlyOffice Document Server 服务
负责生成 JWT 签名的编辑器配置
"""
import jwt
from typing import Optional, Dict, Any
from app.core.config import settings
from app.core.logger import logger


class OnlyOfficeService:
    """OnlyOffice 文档服务器集成"""
    
    def __init__(self):
        self.server_url = settings.ONLYOFFICE_SERVER_URL
        self.jwt_secret = settings.ONLYOFFICE_JWT_SECRET
    
    def _get_document_type(self, file_ext: str) -> str:
        """根据文件扩展名获取 OnlyOffice 文档类型"""
        type_map = {
            "docx": "word",
            "doc": "word",
            "odt": "word",
            "rtf": "word",
            "txt": "word",
            "xlsx": "cell",
            "xls": "cell",
            "ods": "cell",
            "csv": "cell",
            "pptx": "slide",
            "ppt": "slide",
            "odp": "slide",
            "pdf": "word",  # PDF 在 OnlyOffice 中通过 word 类型处理
        }
        return type_map.get(file_ext.lower(), "word")
    
    def generate_editor_config(
        self,
        document_url: str,
        document_key: str,
        document_title: str,
        file_ext: str,
        user_id: Optional[int] = None,
        user_name: Optional[str] = None,
        edit_mode: bool = False,
        callback_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        生成 OnlyOffice 编辑器配置（含 JWT 签名）
        
        Args:
            document_url: 文档的访问 URL（MinIO presigned URL）
            document_key: 文档唯一标识（用于缓存）
            document_title: 文档标题
            file_ext: 文件扩展名
            user_id: 当前用户 ID
            user_name: 当前用户名
            edit_mode: 是否启用编辑模式
            callback_url: 编辑回调 URL（保存时调用）
        
        Returns:
            包含 JWT token 的编辑器配置
        """
        doc_type = self._get_document_type(file_ext)
        
        # 构建编辑器配置
        config = {
            "document": {
                "fileType": file_ext.lower(),
                "key": document_key,
                "title": document_title,
                "url": document_url,
                "permissions": {
                    "edit": edit_mode,
                    "download": True,
                    "print": True,
                    "comment": edit_mode,
                    "review": edit_mode,
                    "copy": True,
                },
            },
            "documentType": doc_type,
            "editorConfig": {
                "mode": "edit" if edit_mode else "view",
                "lang": "zh-CN",
                "callbackUrl": callback_url or "",
                "user": {
                    "id": str(user_id) if user_id else "anonymous",
                    "name": user_name or "匿名用户",
                },
                "customization": {
                    "autosave": edit_mode,
                    "chat": False,
                    "comments": edit_mode,
                    "compactHeader": True,
                    "compactToolbar": True,
                    "feedback": False,
                    "forcesave": False,
                    "help": False,
                    "hideRightMenu": not edit_mode,
                    "hideRulers": not edit_mode,
                    "logo": {
                        "visible": False,
                    },
                    "plugins": False,
                    "toolbarNoTabs": True,
                    "uiTheme": "theme-light",
                },
            },
            "type": "embedded",  # 嵌入模式
            "height": "100%",
            "width": "100%",
        }
        
        # 生成 JWT Token
        token = self._sign_config(config)
        config["token"] = token
        
        logger.debug(f"Generated OnlyOffice config for document: {document_key}")
        
        return {
            "config": config,
            "server_url": self.server_url,
            "api_url": f"{self.server_url}/web-apps/apps/api/documents/api.js",
        }
    
    def _sign_config(self, config: Dict[str, Any]) -> str:
        """使用 JWT 对配置进行签名"""
        try:
            # OnlyOffice v7.2+ 要求的 JWT 格式
            # 需要将配置直接作为 payload
            payload = config.copy()
            
            # OnlyOffice 默认使用 HS256 算法
            token = jwt.encode(
                payload,
                self.jwt_secret,
                algorithm="HS256"
            )
            return token
        except Exception as e:
            logger.error(f"Failed to sign OnlyOffice config: {e}")
            raise


# 单例实例
onlyoffice_service = OnlyOfficeService()
