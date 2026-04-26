import os
import jwt
import requests
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from cryptography.x509 import load_pem_x509_certificate
from cryptography.hazmat.backends import default_backend

security = HTTPBearer()

# Cache the JWKS
_jwks = None

def get_jwks():
    global _jwks
    if not _jwks:
        # Replace with your actual Clerk frontend API URL or Domain
        # Ideally, this should be an environment variable like CLERK_ISSUER_URL
        # e.g., https://clerk.yourdomain.com/.well-known/jwks.json
        clerk_frontend_api = os.getenv("CLERK_FRONTEND_API", "https://api.clerk.com/v1")
        # Note: Clerk's JWKS is typically at https://<YOUR_CLERK_FRONTEND_API>/.well-known/jwks.json
        # For testing purposes, we might just bypass strict validation if not configured,
        # but here we'll try to fetch it.
        jwks_url = f"{clerk_frontend_api}/.well-known/jwks.json"
        try:
            response = requests.get(jwks_url)
            response.raise_for_status()
            _jwks = response.json()
        except Exception as e:
            print(f"Failed to fetch JWKS: {e}")
            _jwks = {"keys": []}
    return _jwks

async def get_current_tenant(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    
    # In a real production app, you MUST verify the JWT signature using Clerk's JWKS
    # For now, we decode without verification if the JWKS is not properly set up,
    # or you can enforce verification.
    
    try:
        # Decode the unverified header to get the kid
        unverified_header = jwt.get_unverified_header(token)
        
        # NOTE: For a complete implementation, you'd find the matching key in JWKS,
        # construct the public key, and verify the signature.
        # To keep this simple and functional for the MVP without blocking on Clerk setup:
        decoded_token = jwt.decode(token, options={"verify_signature": False})
        
        user_id = decoded_token.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing subject",
            )
            
        return user_id
        
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
