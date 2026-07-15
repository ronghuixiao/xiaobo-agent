"""API 认证模块

提供 Bearer Token 认证的 FastAPI 依赖。
"""

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


def create_auth_dependency(api_key: str = ""):
    """创建认证依赖

    Args:
        api_key: 有效的 API key。为空时不启用认证。

    Returns:
        FastAPI Depends 可用的认证函数
    """
    if not api_key:
        # 不启用认证
        return None

    security = HTTPBearer(auto_error=False)

    async def verify_token(
        credentials: HTTPAuthorizationCredentials = Security(security),
    ):
        if credentials is None or credentials.credentials != api_key:
            raise HTTPException(
                status_code=401,
                detail="Invalid or missing API key",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return credentials.credentials

    return Depends(verify_token)
