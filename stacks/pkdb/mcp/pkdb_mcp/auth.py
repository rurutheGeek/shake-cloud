# -*- coding: utf-8 -*-
"""Authentik が出したアクセストークン（JWT）を確かめる。

MCP の認可の仕様どおり、このサーバは OAuth の保護リソースで、トークンを出すのは
Authentik（アプリケーション pkdb-mcp、admins だけが認可できる）。署名・発行者・
宛先（client_id）・期限を確かめ、名前を entry_log の actor に使う。
"""
import anyio.to_thread
import jwt

from mcp.server.auth.provider import AccessToken

ALGORITHMS = ['RS256', 'ES256']


class AuthentikTokenVerifier:
    def __init__(self, issuer, audience, jwks_url=None):
        self.issuer = issuer
        self.audience = audience
        self.jwks = jwt.PyJWKClient(jwks_url or issuer.rstrip('/') + '/jwks/',
                                    cache_keys=True, lifespan=3600, timeout=5)

    def decode(self, token):
        key = self.jwks.get_signing_key_from_jwt(token)
        return jwt.decode(token, key.key, algorithms=ALGORITHMS, audience=self.audience,
                          issuer=self.issuer,
                          options={'require': ['exp', 'iss', 'aud', 'sub']})

    async def verify_token(self, token):
        try:
            claims = await anyio.to_thread.run_sync(self.decode, token)
        except (jwt.PyJWTError, OSError):
            return None
        return AccessToken(
            token=token,
            client_id=str(claims.get('azp') or self.audience),
            scopes=str(claims.get('scope', '')).split(),
            expires_at=int(claims['exp']),
            subject=str(claims['sub']),
            claims=claims,
        )


def actor(token):
    """entry_log の actor。画面（Authentik のユーザ名）と同じ名前に mcp: を付ける。"""
    claims = (token.claims or {}) if token else {}
    name = claims.get('preferred_username') or claims.get('nickname') or (token.subject if token else '')
    return f'mcp:{name or "unknown"}'
