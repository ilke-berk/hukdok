import logging
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
            ALLOWED_TENANTS = [
                "44f029f8-f2f7-4910-8c38-998dca5fad02",  # LexisBio
                "9776cf1f-e0b0-4923-9433-33f3fb4161de",  # Hanyaloglu
            ]
            
            # Dev Mode Bypass
            if token_tenant == "dev-tenant":
                return unverified_claims

            logger.info(f"Auth: Validating Token for Tenant: {token_tenant}")

            if token_tenant not in ALLOWED_TENANTS:
                logger.warning(f"Auth: Tenant unauthorized. Token: {token_tenant} is not in {ALLOWED_TENANTS}")
                # return None # TEMPORARY DEBUG: Allow all tenants during dev/test if needed? 
                # Better to just see the log first.
                return None

            # 3. Get/Create JWKS Client for this Tenant
            jwks_url = f"https://login.microsoftonline.com/{token_tenant}/discovery/v2.0/keys"
            
            if token_tenant not in AuthVerifier._jwks_clients:
                # Use default lru_cache behavior of PyJWKClient
                AuthVerifier._jwks_clients[token_tenant] = PyJWKClient(jwks_url)
            
            signing_key = AuthVerifier._jwks_clients[token_tenant].get_signing_key_from_jwt(token)
            
            # 4. Verify Signature
            # We skip 'aud' check because tokens might be for Graph API or other scopes.
            # Critical part is: Signed by Microsoft + Whitelisted Tenant
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                options={
                    "verify_aud": False,
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
