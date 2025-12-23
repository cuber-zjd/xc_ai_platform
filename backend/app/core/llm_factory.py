from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel
from app.core.config import settings
from app.core.logger import logger

# Langfuse v3 uses a different import path
try:
    from langfuse.callback import CallbackHandler as LangfuseCallbackHandler
except ImportError:
    # Fallback for langfuse v3.x
    try:
        from langfuse import CallbackHandler as LangfuseCallbackHandler
    except ImportError:
        LangfuseCallbackHandler = None  # type: ignore
        logger.warning("LangFuse CallbackHandler not available, tracing disabled")


class LLMFactory:
    """
    Factory to create configured LLM instances with Tracing (LangFuse).
    """

    @staticmethod
    def get_model(
        model_name: str = "ep-20250716092812-ng6hc",  # Default or configure in settings
        api_key: str = "8fd7cc00-8433-4843-8231-6d96853861bc",
        base_url: str = "https://ark.cn-beijing.volces.com/api/v3",
        temperature: float = 0.0,
        streaming: bool = True,
        json_mode: bool = False
    ) -> BaseChatModel:
        """
        Get a Chat Model instance.
        """
        callbacks = []
        
        # Tracing Handler (optional)
        if LangfuseCallbackHandler is not None:
            try:
                langfuse_handler = LangfuseCallbackHandler(
                    public_key=settings.LANGFUSE_PUBLIC_KEY,
                    secret_key=settings.LANGFUSE_SECRET_KEY,
                    host=settings.LANGFUSE_HOST
                )
                callbacks.append(langfuse_handler)
            except Exception as e:
                logger.warning(f"Failed to initialize LangFuse handler: {e}")

        # Configure model kwargs
        model_kwargs = {}
        if json_mode:
            model_kwargs["response_format"] = {"type": "json_object"}

        try:
            llm = ChatOpenAI(
                model=model_name,
                temperature=temperature,
                api_key=api_key,
                base_url=base_url,
                streaming=streaming,
                callbacks=callbacks if callbacks else None,
                model_kwargs=model_kwargs
            )
            return llm
        except Exception as e:
            logger.error(f"Failed to create LLM: {e}")
            raise e
