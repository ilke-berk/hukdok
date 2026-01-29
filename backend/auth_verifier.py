import os
import json
import base64
import time
import logging
from typing import Dict, Optional, Any

logger = logging.getLogger("AuthVerifier")

class AuthVerifier:
    """
    Validates Microsoft Azure AD JWT Tokens without external crypto libraries (Plan B).
    Performs critical checks: Expiration (exp) and Tenant ID (tid).
    
    WARNING: This does NOT verify the cryptographic signature. 
    It is suitable for internal tools on localhost, but for public production, 
    use 'pyjwt' with JWKS verification.
    """
    
    @staticmethod
    def _decode_base64_url(data: str) -> bytes:
        """Helper to decode Base64URL encoded strings."""
        padding = '=' * (4 - (len(data) % 4))
        return base64.urlsafe_b64decode(data + padding)

    @staticmethod
    def verify_token(token: str) -> Optional[Dict[str, Any]]:
        """
        Parses and validates the JWT token.
        
        Args:
            token: The Bearer token string (header.payload.signature)
            
        Returns:
            Dict of claims if valid, None otherwise.
        """
        try:
            if not token:
                logger.warning("Auth: Token is empty")
                return None
                
            parts = token.split('.')
            if len(parts) != 3:
                logger.warning("Auth: Invalid token format (not 3 parts)")
                return None
            
            # Decode Payload (Part 2)
            payload_json = AuthVerifier._decode_base64_url(parts[1]).decode('utf-8')
            claims = json.loads(payload_json)
            
            # 1. Check Expiration (exp)
            current_time = time.time()
            exp = claims.get("exp")
            if not exp or current_time > exp:
                logger.warning(f"Auth: Token expired. Exp: {exp}, Now: {current_time}")
                return None
                
            # 2. Check Tenant ID (tid)
            # We enforce that the token comes from OUR tenant
            expected_tenant = os.getenv("SHAREPOINT_TENANT_ID") or os.getenv("VITE_AZURE_TENANT_ID")
            token_tenant = claims.get("tid")
            
            if expected_tenant and token_tenant != expected_tenant:
                logger.warning(f"Auth: Tenant mismatch. Token: {token_tenant}, Expected: {expected_tenant}")
                return None
                
            # Log success (debug only)
            # logger.debug(f"Auth: Token valid for user {claims.get('preferred_username') or claims.get('upn')}")
            
            return claims
            
        except Exception as e:
            logger.error(f"Auth: Token validation error: {e}")
            return None

    @staticmethod
    def get_user_from_token(token: str) -> str:
        """Extracts username/email from token if valid."""
        claims = AuthVerifier.verify_token(token)
        if claims:
            return claims.get("preferred_username") or claims.get("upn") or claims.get("email") or "Unknown"
        return None
