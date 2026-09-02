"""Central error normalizer for MCP tool handlers (Lot 2C).

Replaces 14× duplicated `except (ValueError,WpmError,RuntimeError)` blocks.
Preserves FastMCP registration by keeping the original signature via
`__signature__` and `__annotations__`.
"""

from __future__ import annotations

import functools
import inspect
import logging
from collections.abc import Callable

from wpm_mcp_server.core.errors import WpmError

logger = logging.getLogger(__name__)


def tool_errors(_func: Callable | None = None, *, prefix_value_error: str | None = None):
    """Normalize (ValueError, WpmError, RuntimeError) -> {"error": True, ...}.

    Usage:
        @mcp.tool(...)
        @tool_errors
        def my_tool(...): ...

        @mcp.tool(...)
        @tool_errors(prefix_value_error="invalid type: ")
        async def store_entry(...): ...

    Handles both `def` and `async def`; preserves signature for FastMCP.
    """

    def decorator(func: Callable):
        is_async = inspect.iscoroutinefunction(func)
        sig = inspect.signature(func)

        if is_async:

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
                try:
                    return await func(*args, **kwargs)
                except (ValueError, WpmError, RuntimeError) as exc:
                    logger.debug("tool %s failed: %s", func.__name__, exc, exc_info=True)
                    if isinstance(exc, ValueError) and prefix_value_error:
                        return {"error": True, "message": f"{prefix_value_error}{exc}"}
                    return {"error": True, "message": str(exc)}

            async_wrapper.__signature__ = sig  # type: ignore[attr-defined]
            async_wrapper.__annotations__ = getattr(func, "__annotations__", {})
            return async_wrapper
        else:

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
                try:
                    return func(*args, **kwargs)
                except (ValueError, WpmError, RuntimeError) as exc:
                    logger.debug("tool %s failed: %s", func.__name__, exc, exc_info=True)
                    if isinstance(exc, ValueError) and prefix_value_error:
                        return {"error": True, "message": f"{prefix_value_error}{exc}"}
                    return {"error": True, "message": str(exc)}

            sync_wrapper.__signature__ = sig  # type: ignore[attr-defined]
            sync_wrapper.__annotations__ = getattr(func, "__annotations__", {})
            return sync_wrapper

    if _func is not None and callable(_func) and prefix_value_error is None:
        # Used as @tool_errors without parens
        return decorator(_func)
    return decorator
