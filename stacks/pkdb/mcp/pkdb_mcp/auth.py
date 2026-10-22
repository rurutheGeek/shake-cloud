# -*- coding: utf-8 -*-
"""Authentik が出したアクセストークン（JWT）を確かめる。

MCP の認可の仕様どおり、このサーバは OAuth の保護リソースで、トークンを出すのは
Authentik（アプリケーション pkdb-mcp、admins だけが認可できる）。署名・発行者・
宛先（client_id）・期限を確かめ、名前を entry_log の actor に使う。
"""
import base64
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request

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


class BasicExchange:
    """`Authorization: Basic <ユーザ名:アプリパスワード>` を、OAuth のトークンへ引き換える。

    ブラウザの無い機械や、OAuth のログインを持たない MCP クライアントのため。
    どのクライアントにもあるヘッダの設定だけで使える。引き換えは認可サーバの
    トークン窓口への client_credentials（Authentik ではアプリパスワードを password に
    渡す形）で、出てきたトークンは OAuth と同じ確かめ方をする。期限まで覚えておき、
    同じ資格情報で何度も引き換えない。
    """

    def __init__(self, issuer, client_id, scope='openid profile'):
        self.issuer = issuer
        self.client_id = client_id
        self.scope = scope
        self.token_endpoint = None
        self.cache = {}

    def _endpoint(self):
        if self.token_endpoint is None:
            url = self.issuer.rstrip('/') + '/.well-known/openid-configuration'
            with urllib.request.urlopen(url, timeout=5) as response:
                self.token_endpoint = json.load(response)['token_endpoint']
        return self.token_endpoint

    def exchange(self, username, password):
        key = hashlib.sha256(f'{username}\0{password}'.encode()).hexdigest()
        cached = self.cache.get(key)
        if cached and cached[1] > time.time() + 30:
            return cached[0]
        body = urllib.parse.urlencode({
            'grant_type': 'client_credentials', 'client_id': self.client_id,
            'username': username, 'password': password, 'scope': self.scope}).encode()
        try:
            with urllib.request.urlopen(urllib.request.Request(self._endpoint(), data=body),
                                        timeout=10) as response:
                data = json.load(response)
        except (urllib.error.URLError, ValueError, KeyError):
            return None
        token = data.get('access_token')
        if not token:
            return None
        self.cache = {k: v for k, v in self.cache.items() if v[1] > time.time()}
        self.cache[key] = (token, time.time() + int(data.get('expires_in', 300)))
        return token


class BasicToBearer:
    """Basic の資格情報を Bearer のトークンへ書き換えてから、MCP のアプリへ渡す ASGI。"""

    def __init__(self, app, exchange):
        self.app = app
        self.exchange = exchange

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http':
            headers = [(name, value) for name, value in scope['headers'] if name != b'authorization']
            value = dict(scope['headers']).get(b'authorization', b'')
            if value[:6].lower() == b'basic ':
                try:
                    username, _, password = base64.b64decode(value[6:]).decode().partition(':')
                except (ValueError, UnicodeDecodeError):
                    username = password = ''
                token = (await anyio.to_thread.run_sync(self.exchange.exchange, username, password)
                         if username and password else None)
                # 引き換えられなければ資格情報なしとして渡し、401 と WWW-Authenticate を返させる。
                if token:
                    headers.append((b'authorization', b'Bearer ' + token.encode()))
                scope = dict(scope, headers=headers)
        await self.app(scope, receive, send)
