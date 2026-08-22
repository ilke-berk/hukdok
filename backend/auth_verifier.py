import logging
import os
from typing import Dict, Optional, Any
import jwt
from jwt import PyJWKClient

logger = logging.getLogger("AuthVerifier")

class AuthVerifier:
    """
    Validates Microsoft Azure AD JWT Tokens using PyJWT with cryptographic signature verification.
    Fetches public keys (JWKS) from Microsoft's endpoint.
    """
    
    # Simple cache for JWKS clients to avoid re-creation
    _jwks_clients = {}

    # G096: access token'da bulunması ŞART olan delegated scope. Frontend MSAL
    # `api://<client_id>/access_as_user` ister (`frontend/src/config/msalConfig.ts`);
    # bu scope'u taşımayan token (örn. aynı uygulamanın ID token'ı) reddedilir.
    REQUIRED_SCOPE = "access_as_user"

    @staticmethod
    def _expected_issuers(tenant_id: str) -> list:
        """`tid`'den türetilen kabul edilebilir `iss` değerleri.

        Azure AD, app registration'daki `accessTokenAcceptedVersion` ayarına göre
        v2 (`login.microsoftonline.com/{tid}/v2.0`) ya da v1 (`sts.windows.net/{tid}/`)
        issuer basar; hangisinin geldiği repodan bilinemez, ikisi de kabul edilir.
        Sabit tenant gömülmez — `ALLOWED_TENANTS`'taki her tenant kendi iss'iyle geçer.
        """
        return [
            f"https://login.microsoftonline.com/{tenant_id}/v2.0",
            f"https://sts.windows.net/{tenant_id}/",
        ]

    @staticmethod
    def _has_required_scope(claims: Dict[str, Any]) -> bool:
        """G096: `scp` claim'i boşlukla ayrılmış scope listesidir; içinde
        `REQUIRED_SCOPE` yoksa token bu API için verilmemiştir (ID token ya da
        başka bir kaynağa ait access token). Ret sebebi WARNING ile loglanır —
        gözlenen `scp` değeri yazılır, token'ın kendisi ASLA yazılmaz.

        Gerekçe: G092 gözlem turu (2026-08-22, gerçek Azure AD girişi, 10
        doğrulama) sapma göstermedi; gerçek token `access_as_user` taşıyor.
        """
        scp = claims.get("scp")
        scopes = scp.split() if isinstance(scp, str) else []
        if AuthVerifier.REQUIRED_SCOPE in scopes:
            return True
        logger.warning(
            "Auth: scope eksik — scp=%r icinde %r yok, token reddedildi.",
            scp, AuthVerifier.REQUIRED_SCOPE,
        )
        return False

    @staticmethod
    def verify_token(token: str) -> Optional[Dict[str, Any]]:
        """
        Parses and validates the JWT token with signature verification.
        """
        try:
            if not token:
                logger.warning("Auth: Token is empty")
                return None
                
            # 1. Decode unverified header/payload to get Tenant ID
            # We don't verify signature here yet, just need 'tid' to find the right keys
            unverified_claims = jwt.decode(token, options={"verify_signature": False})
            token_tenant = unverified_claims.get("tid")
            
            # 2. Check Tenant Whitelist
            ALLOWED_TENANTS = set(
                t.strip() for t in os.getenv("ALLOWED_TENANTS", "").split(",") if t.strip()
            )
            
            # Dev Mode Bypass (G5) — imzasız token kabulü yalnızca ÜÇ koşul birden
            # sağlanırsa: ENV=development + ALLOW_DEV_TENANT=true + DEV_MODE=true.
            # Prod .env'de DEV_MODE false/tanımsız olduğundan bu yol prod'da kapalıdır;
            # kombinasyon eksikse api.py başlangıçta CRITICAL log basar.
            if (os.getenv("ENV") == "development" and os.getenv("ALLOW_DEV_TENANT") == "true"
                    and os.getenv("DEV_MODE", "").lower() == "true"
                    and token_tenant == "dev-tenant"):
                logger.warning("Auth: DEV bypass aktif — imzasız 'dev-tenant' token kabul edildi.")
                return unverified_claims

            logger.info(f"Auth: Validating Token for Tenant: {token_tenant}")

            if token_tenant not in ALLOWED_TENANTS:
                logger.warning(f"Auth: Tenant unauthorized: {token_tenant}")
                return None

            # 3. Get/Create JWKS Client for this Tenant
            jwks_url = f"https://login.microsoftonline.com/{token_tenant}/discovery/v2.0/keys"
            
            if token_tenant not in AuthVerifier._jwks_clients:
                # Use default lru_cache behavior of PyJWKClient
                AuthVerifier._jwks_clients[token_tenant] = PyJWKClient(jwks_url)
            
            signing_key = AuthVerifier._jwks_clients[token_tenant].get_signing_key_from_jwt(token)

            # 4. Verify Signature + Audience
            # aud YALNIZ "api://<client_id>" (G096). Çıplak "<client_id>" audience'ı
            # aynı uygulamanın ID token'ında gelir; kabul edilseydi ID token access
            # token yerine geçerdi (O4 bulgusu). G092 gözlemi (2026-08-22, 10 doğrulama,
            # 0 sapma) gerçek access token'ın api:// biçiminde geldiğini doğruladı.
            client_id = os.getenv("AZURE_CLIENT_ID")
            if not client_id:
                logger.error("Auth: AZURE_CLIENT_ID env var is not set")
                return None

            allowed_audiences = [f"api://{client_id}"]

            # 5. Issuer (G092): `iss` tid'den türetilen iki biçimden biri olmalı.
            # PyJWT `issuer=` listesini kabul eder; `iss` yoksa MissingRequiredClaimError,
            # listede yoksa InvalidIssuerError — ikisi de InvalidTokenError'a düşer.
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=allowed_audiences,
                issuer=AuthVerifier._expected_issuers(token_tenant),
                options={
                    "verify_aud": True,
                    "verify_iss": True,
                    "verify_exp": True
                }
            )

            # 6. Scope (G096): imza/aud/iss/exp geçti; `scp` içinde access_as_user şart.
            if not AuthVerifier._has_required_scope(claims):
                return None
            return claims
            
        except jwt.ExpiredSignatureError:
            logger.warning("Auth: Token expired")
        except jwt.InvalidTokenError as e:
            logger.error(f"Auth: Invalid token: {e}")
        except Exception as e:
            logger.error(f"Auth: Unexpected validation error: {e}")
            
        return None

    @staticmethod
    def get_user_from_token(token: str) -> str:
        """Extracts username/email from token if valid."""
        claims = AuthVerifier.verify_token(token)
        if claims:
            return claims.get("preferred_username") or claims.get("upn") or claims.get("email") or "Unknown"
        return None
