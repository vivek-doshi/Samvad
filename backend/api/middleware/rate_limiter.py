# Prevents brute force on /auth/login
# Note 1: This module is reserved for rate limiting middleware that protects
# the /auth/login endpoint against brute-force password guessing attacks.
#
# Note 2: Brute force attacks try many passwords against one account (or one
# password against many accounts — "credential stuffing"). Without rate limiting,
# an attacker could try thousands of passwords per second.
#
# Note 3: A common approach using slowapi (a FastAPI-compatible rate limiter):
#
#   from slowapi import Limiter
#   from slowapi.util import get_remote_address
#
#   limiter = Limiter(key_func=get_remote_address)
#
#   @router.post("/login")
#   @limiter.limit("5/minute")   # max 5 login attempts per IP per minute
#   async def login(request: Request, ...):
#       ...
#
# Note 4: For production, also consider:
# - Exponential backoff (increasing delay after each failed attempt)
# - Account lockout after N consecutive failures (tracked in audit_log)
# - CAPTCHA after the first 3 failures
# - IP-based blocking via Nginx (infra/nginx/nginx.conf)
