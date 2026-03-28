# Security Deployment Guide - Docker Compose

This guide explains how to deploy the security fixes to your docker-compose environments (local and production).

---

## 🚀 Quick Start

### 1. Install New Dependencies

```bash
# Backend service
cd /Users/Omarjan/Projects/kitabim-ai/services/backend
pip install slowapi>=0.1.9

# Or rebuild Docker images (recommended)
cd /Users/Omarjan/Projects/kitabim-ai
docker-compose build backend worker
```

### 2. Generate Security Secrets

```bash
# Generate JWT Secret (64+ characters)
python3 -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(64))"

# Generate IP Salt (32+ characters)
python3 -c "import secrets; print('IP_SALT=' + secrets.token_urlsafe(32))"
```

Save these outputs - you'll add them to `.env` next.

### 3. Update Environment Configuration

Edit your `.env` file in the project root:

```bash
# Required Security Updates
JWT_SECRET_KEY=<paste-generated-secret-here>
IP_SALT=<paste-generated-salt-here>
CORS_ORIGINS=http://localhost:30080,http://localhost:3000
ENVIRONMENT=development

# For Production (.env or deploy/gcp/.env)
ENVIRONMENT=production
CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
```

### 4. Restart Services

```bash
# Local development
./deploy/local/rebuild-and-restart.sh all

# Production (GCP)
./deploy/gcp/scripts/deploy.sh [tag]
```

---

## 📋 Deployment Checklist

### Local Development Environment

- [ ] Generated `JWT_SECRET_KEY` (64+ chars)
- [ ] Generated `IP_SALT` (32+ chars)
- [ ] Updated root `.env` file with secrets
- [ ] Set `CORS_ORIGINS=http://localhost:30080,http://localhost:3000`
- [ ] Set `ENVIRONMENT=development`
- [ ] Rebuilt and restarted services: `./deploy/local/rebuild-and-restart.sh all`
- [ ] Verified backend health: `curl http://localhost:30800/health`
- [ ] Tested login functionality

### Production Environment (GCP)

- [ ] Generated production `JWT_SECRET_KEY` (different from dev!)
- [ ] Generated production `IP_SALT` (different from dev!)
- [ ] Updated `deploy/gcp/.env` with production secrets
- [ ] Set `CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com`
- [ ] Set `ENVIRONMENT=production`
- [ ] Updated OAuth redirect URIs to production URLs
- [ ] Verified SSL/TLS certificates are valid
- [ ] Deployed services: `./deploy/gcp/scripts/deploy.sh [tag]`
- [ ] Verified HTTPS redirection works
- [ ] Tested authentication flow
- [ ] Monitored logs for errors

---

## 🔧 Environment Variables Reference

### Required (Critical)

```bash
# Authentication
JWT_SECRET_KEY=<64+ character random string>
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Privacy & Security
IP_SALT=<32+ character random string>
CORS_ORIGINS=http://localhost:30080,https://yourdomain.com
ENVIRONMENT=development  # or 'production'

# Database
DATABASE_URL=postgresql://user:password@host:5432/kitabim-ai

# Redis
REDIS_URL=redis://redis:6379/0
```

### Optional (OAuth Providers)

```bash
# Google OAuth
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:30080/api/auth/google/callback

# Facebook OAuth
FACEBOOK_CLIENT_ID=your-facebook-app-id
FACEBOOK_CLIENT_SECRET=your-facebook-secret
FACEBOOK_REDIRECT_URI=http://localhost:30080/api/auth/facebook/callback

# Twitter OAuth
TWITTER_CLIENT_ID=your-twitter-client-id
TWITTER_CLIENT_SECRET=your-twitter-client-secret
TWITTER_REDIRECT_URI=http://localhost:30080/api/auth/twitter/callback
```

---

## 🧪 Testing After Deployment

### 1. Health Check
```bash
# Local
curl http://localhost:30800/health

# Production
curl https://yourdomain.com/api/health
```

Expected response:
```json
{"status": "ok"}
```

### 2. Rate Limiting Test
```bash
# Try 15 login attempts in quick succession (should be blocked after 10)
for i in {1..15}; do
  curl -i http://localhost:30800/api/auth/google/login
  echo "Attempt $i"
  sleep 1
done
```

Expected: After 10 attempts, you should see `429 Too Many Requests`

### 3. CORS Test
```bash
# Should be rejected (wrong origin)
curl -H "Origin: https://evil.com" \
     -H "Access-Control-Request-Method: POST" \
     -H "Access-Control-Request-Headers: Content-Type" \
     -X OPTIONS http://localhost:30800/api/auth/me

# Should be allowed (correct origin)
curl -H "Origin: http://localhost:30080" \
     -H "Access-Control-Request-Method: POST" \
     -H "Access-Control-Request-Headers: Content-Type" \
     -X OPTIONS http://localhost:30800/api/auth/me
```

### 4. HTTPS Enforcement (Production Only)
```bash
# Should redirect to HTTPS
curl -I http://yourdomain.com/api/health

# Should show 301 redirect to https://
```

### 5. Security Headers Check
```bash
curl -I http://localhost:30800/api/health
```

Expected headers:
```
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block
Content-Security-Policy: default-src 'self'; ...
```

### 6. IP Hashing Test
```bash
# Login to the application
# Then check database
docker-compose exec backend psql $DATABASE_URL -c \
  "SELECT id, email, last_login_ip FROM users LIMIT 5;"
```

Expected: `last_login_ip` should be 16-character hex hashes, not raw IPs.

---

## 🐛 Troubleshooting

### Issue: "JWT_SECRET_KEY environment variable is required"

**Solution:**
```bash
# Check if .env is loaded
docker-compose exec backend env | grep JWT_SECRET_KEY

# If empty, add to .env and restart
docker-compose restart backend worker
```

### Issue: "429 Too Many Requests" on first login

**Solution:**
```bash
# Clear rate limiting (Redis)
docker-compose exec redis redis-cli FLUSHALL

# Or wait 1 minute for rate limit to reset
```

### Issue: CORS errors in browser console

**Solution:**
1. Check `CORS_ORIGINS` includes your frontend URL
2. Restart backend: `docker-compose restart backend`
3. Clear browser cache
4. Verify origin in Network tab matches exactly

### Issue: OAuth callback fails with "Invalid origin"

**Solution:**
1. Update `GOOGLE_REDIRECT_URI` (and other OAuth URIs) in `.env`
2. Update same URIs in OAuth provider console (Google/Facebook/Twitter)
3. Ensure URIs match exactly (http vs https, port numbers, trailing slashes)

### Issue: Backend won't start in production

**Solution:**
```bash
# Check logs
docker-compose logs backend

# Common causes:
# - JWT_SECRET_KEY too short (< 32 chars)
# - Missing required environment variables
# - Database connection failure

# Verify all required vars are set
docker-compose exec backend env | grep -E "(JWT_SECRET_KEY|IP_SALT|ENVIRONMENT)"
```

---

## 📊 Monitoring & Logs

### View Logs
```bash
# All services
docker-compose logs -f

# Backend only
docker-compose logs -f backend

# Last 100 lines
docker-compose logs --tail=100 backend

# Filter for security events
docker-compose logs backend | grep -i "rate limit\|jwt\|oauth"
```

### Important Log Patterns to Monitor

**Failed Authentication:**
```
WARNING: Failed login attempt from IP ...
```

**Rate Limiting:**
```
INFO: Rate limit exceeded for IP ...
```

**JWT Issues:**
```
ERROR: JWT secret validation failed
WARNING: Invalid token received
```

**CORS Violations:**
```
WARNING: CORS request from unauthorized origin ...
```

---

## 🔄 Updating Secrets (Rotation)

### Why Rotate Secrets?
- Compromised secrets
- Employee/contractor offboarding
- Regular security hygiene (every 90 days recommended)

### How to Rotate

1. **Generate new secrets:**
```bash
python3 -c "import secrets; print('NEW_JWT_SECRET=' + secrets.token_urlsafe(64))"
python3 -c "import secrets; print('NEW_IP_SALT=' + secrets.token_urlsafe(32))"
```

2. **Update .env file:**
```bash
# Replace old values with new ones
vim .env
```

3. **Restart services:**
```bash
docker-compose restart backend worker
```

4. **Verify no errors:**
```bash
docker-compose logs backend | grep -i error
```

**Note:** Rotating JWT_SECRET_KEY will invalidate all existing access tokens. Users will need to log in again.

---

## 🔐 Production Security Hardening

### Additional Production Steps

1. **Enable SSL/TLS (Production nginx):**
   - Verify Let's Encrypt certificates are valid
   - Check `deploy/gcp/nginx/conf.d/` configuration
   - Test HTTPS enforcement

2. **Database Security:**
   - Use strong PostgreSQL password
   - Enable SSL connections
   - Restrict network access

3. **Firewall Rules:**
   - Block direct access to backend (port 30800)
   - Only allow nginx (port 80/443)
   - Restrict Redis access to internal network

4. **Backup Secrets:**
   - Store secrets in secure vault (1Password, HashiCorp Vault, etc.)
   - Never commit `.env` to git
   - Use `.env.example` for template only

5. **Enable Audit Logging:**
   - Log all authentication events
   - Monitor rate limit violations
   - Set up alerts for suspicious activity

---

## 📞 Support

If you encounter issues:

1. **Check logs:** `docker-compose logs backend`
2. **Verify health:** `curl http://localhost:30800/health`
3. **Review checklist:** Ensure all steps completed
4. **Check environment:** `docker-compose exec backend env`

For urgent security issues:
- Stop affected services immediately
- Review access logs
- Rotate compromised secrets
- Investigate breach scope

---

## 🎯 Next Steps

After successful deployment:

1. ✅ Verify all tests pass
2. ✅ Monitor logs for 24 hours
3. ✅ Document any custom configurations
4. 🔄 Schedule secret rotation (90 days)
5. 🔄 Review and fix medium-severity issues
6. 🔄 Set up automated security scanning
7. 🔄 Create disaster recovery plan

---

**Deployment complete!** 🎉

Your application now has enterprise-grade security for authentication, CORS, rate limiting, and privacy compliance.
