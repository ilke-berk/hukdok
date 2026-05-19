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
            
            # Dev Mode Bypass — yalnızca development ortamında ve açıkça etkinleştirilmişse
            if (os.getenv("ENV") == "development" and os.getenv("ALLOW_DEV_TENANT") == "true"
                    and token_tenant == "dev-tenant"):
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
            # aud, bu uygulama için verilmiş token'ları kabul etsin diye client_id'ye sabitlenir.
            # Azure AD scope formatına göre token'ın aud'u "api://<client_id>" veya direkt "<client_id>"
            # olabilir; ikisini de geçerli kabul ediyoruz.
            client_id = os.getenv("AZURE_CLIENT_ID")
            if not client_id:
                logger.error("Auth: AZURE_CLIENT_ID env var is not set")
                return None

            allowed_audiences = [client_id, f"api://{client_id}"]

            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=allowed_audiences,
                options={
                    "verify_aud": True,
                    "verify_exp": True
                }
            )
            
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
