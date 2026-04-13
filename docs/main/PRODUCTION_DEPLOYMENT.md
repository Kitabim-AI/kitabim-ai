# Production Deployment Guide - Kitabim.AI

This guide walks you through deploying the security-hardened Kitabim.AI application to production on GCP.

---

## ✅ What's Already Done

- ✅ Production secrets generated (JWT_SECRET_KEY, IP_SALT)
- ✅ Production .env file created with security configurations
- ✅ CORS configured for `https://kitabim.ai` and `https://www.kitabim.ai`
- ✅ Environment set to `production` (enables strict security mode)
- ✅ All critical and high-severity security fixes applied

---

## 📋 Pre-Deployment Checklist

### 1. Complete the .env File

Edit `deploy/gcp/.env` and replace all `FILL_IN` values:

```bash
cd /Users/Omarjan/Projects/kitabim-ai/deploy/gcp
vim .env  # or use your preferred editor
```

**Required Values to Update:**

- [ ] `DATABASE_URL` - Replace `FILL_IN` with your Cloud SQL password
  ```bash
  DATABASE_URL=postgresql://kitabim:YOUR_DB_PASSWORD@10.158.0.5:5432/kitabim-ai
  ```

- [ ] `GEMINI_API_KEY` - Your production Gemini API key
  ```bash
  GEMINI_API_KEY=YOUR_PRODUCTION_GEMINI_KEY
  ```

- [ ] `GOOGLE_CLIENT_ID` - Production Google OAuth client ID
  ```bash
  GOOGLE_CLIENT_ID=YOUR_PROD_CLIENT_ID.apps.googleusercontent.com
  ```

- [ ] `GOOGLE_CLIENT_SECRET` - Production Google OAuth secret
  ```bash
  GOOGLE_CLIENT_SECRET=YOUR_PROD_CLIENT_SECRET
  ```

- [ ] `ADMIN_EMAILS` - Comma-separated admin email addresses
  ```bash
  ADMIN_EMAILS=admin@yourdomain.com,another@yourdomain.com
  ```

### 2. Verify Google OAuth Configuration

**Important:** Update your Google OAuth redirect URIs in the [Google Cloud Console](https://console.cloud.google.com/apis/credentials):

Add production callback URL:
```
https://kitabim.ai/api/auth/google/callback
```

### 3. Verify Domain & SSL

Ensure your domain is configured:
- [ ] DNS points to your GCP VM
- [ ] SSL certificate is valid (Let's Encrypt)
- [ ] Nginx is configured for HTTPS

---

## 🚀 Deployment Steps (Automated)

The most reliable way to deploy is using the production deployment script. This script handles:
1. Building images for `linux/amd64` architecture.
2. Pushing them to the GCP Artifact Registry.
3. SSHing into the VM to pull changes and restart services.
4. Restarting Nginx to refresh upstream connections.

### Run the Deployment Script

From the repository root on your local machine:

```bash
# Deploy with a specific tag (optional)
./deploy/gcp/scripts/deploy.sh v1.0.0

# Deploy with automatic git short-sha tag
./deploy/gcp/scripts/deploy.sh
```

---

## 🛠️ Manual Deployment (Alternative)

If the script fails or you need manual control, follow these steps:

### Step 1: Build & Push Images
```bash
# Use buildkit for faster builds
export DOCKER_BUILDKIT=1
export REGISTRY="us-south1-docker.pkg.dev/YOUR_PROJECT_ID/kitabim"
export IMAGE_TAG=$(git rev-parse --short HEAD)

# Build
docker build -f Dockerfile.backend --platform linux/amd64 -t ${REGISTRY}/kitabim-backend:${IMAGE_TAG} .
docker build -f Dockerfile.worker --platform linux/amd64 -t ${REGISTRY}/kitabim-worker:${IMAGE_TAG} .
docker build -f apps/frontend/Dockerfile --platform linux/amd64 -t ${REGISTRY}/kitabim-frontend:${IMAGE_TAG} .

# Push
docker push ${REGISTRY}/kitabim-backend:${IMAGE_TAG}
docker push ${REGISTRY}/kitabim-worker:${IMAGE_TAG}
docker push ${REGISTRY}/kitabim-frontend:${IMAGE_TAG}
```

### Step 2: Update Server
SSH into the production server and run:
```bash
cd /opt/kitabim
git pull
REGISTRY=... IMAGE_TAG=... docker compose -f deploy/gcp/docker-compose.yml up -d
```


### Step 4: Run Database Migrations (if needed)

This project uses raw SQL migration files — **not Alembic**. Run migrations using the migration script from your local machine:

```bash
# From the repository root
./scripts/run_migration_prod.sh <migration_number>

# Example: apply migration 034
./scripts/run_migration_prod.sh 034
```

The script connects directly to the production database via `deploy/gcp/.env` and runs the SQL file from `packages/backend-core/migrations/`.

---

## 🧪 Post-Deployment Verification

### 1. Health Check

```bash
curl https://kitabim.ai/api/health
```

Expected response:
```json
{"status":"ok"}
```

### 2. Security Headers Check

```bash
curl -I https://kitabim.ai/api/auth/health
```

Verify these headers are present:
- ✅ `X-Frame-Options: DENY`
- ✅ `X-Content-Type-Options: nosniff`
- ✅ `X-XSS-Protection: 1; mode=block`
- ✅ `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- ✅ `Content-Security-Policy: ...`

### 3. HTTPS Redirect Test

```bash
curl -I http://kitabim.ai/api/health
```

Should return `301` or `302` redirect to `https://kitabim.ai/api/health`

### 4. Authentication Test

1. Visit `https://kitabim.ai`
2. Click "Login with Google"
3. Complete OAuth flow
4. Verify you're logged in successfully
5. Check that admin features work (if you're an admin)

### 5. Rate Limiting Test

```bash
# Try 15 login attempts (should be blocked after 10)
for i in {1..15}; do
  curl -s -o /dev/null -w "Attempt $i: %{http_code}\n" \
    https://kitabim.ai/api/auth/google/login
  sleep 0.5
done
```

Expected: HTTP 429 (Too Many Requests) after 10 attempts

### 6. CORS Test

From browser console on a different domain:
```javascript
fetch('https://kitabim.ai/api/auth/me', {
  credentials: 'include'
})
```

Should fail with CORS error (expected behavior - security working!)

### 7. Check Logs for Errors

```bash
# On production server
docker-compose logs backend | grep -i error
docker-compose logs worker | grep -i error
```

Should see no critical errors. Look for:
- ✅ "JWT secret key validated successfully"
- ✅ Database connection successful
- ✅ No authentication errors

---

## 🔐 Production Security Checklist

After deployment, verify:

- [ ] **HTTPS Only** - All traffic redirected to HTTPS
- [ ] **Security Headers** - All headers present (X-Frame-Options, CSP, etc.)
- [ ] **CORS** - Only `kitabim.ai` allowed, wildcard blocked
- [ ] **Rate Limiting** - Login attempts limited (10/min)
- [ ] **JWT Validation** - Application starts successfully
- [ ] **IP Hashing** - New logins store hashed IPs only
- [ ] **Error Messages** - Generic messages shown to users
- [ ] **OAuth** - Production redirect URIs configured
- [ ] **Secrets** - .env file never committed to git
- [ ] **Database** - Using strong password
- [ ] **Firewall** - Only ports 80/443 open to public

---

## 📊 Monitoring

### View Live Logs

```bash
# All services
docker-compose logs -f

# Backend only
docker-compose logs -f backend

# Last 100 lines
docker-compose logs --tail=100 backend
```

### Monitor Key Metrics

Watch for:
- Failed login attempts
- Rate limit violations
- JWT validation errors
- Database connection issues
- CORS violations

```bash
# Failed authentications
docker-compose logs backend | grep -i "failed login"

# Rate limiting
docker-compose logs backend | grep -i "rate limit"

# Security events
docker-compose logs backend | grep -E "(CORS|JWT|oauth)"
```

---

## 🔄 Rolling Back

If something goes wrong:

```bash
# On production server
docker-compose down

# Restore previous .env if needed
cp .env.backup .env

# Start with previous image version
export IMAGE_TAG=previous-timestamp
docker-compose up -d
```

---

## 🆘 Troubleshooting

### Issue: "JWT_SECRET_KEY environment variable is required"

**Fix:** Verify `.env` file is in `/path/to/kitabim-ai/deploy/gcp/.env`

```bash
cat .env | grep JWT_SECRET_KEY
```

Should show the long secret, not `FILL_IN`.

### Issue: OAuth callback fails

**Fix:** Verify redirect URI matches exactly in Google Console:
- Production: `https://kitabim.ai/api/auth/google/callback`
- No trailing slashes
- HTTPS (not HTTP)

### Issue: CORS errors in browser

**Fix:** Check `CORS_ORIGINS` in `.env`:
```bash
CORS_ORIGINS=https://kitabim.ai,https://www.kitabim.ai
```

Must match frontend domain exactly (https, no trailing slash).

### Issue: Database connection fails

**Fix:** Verify Cloud SQL private IP is accessible:
```bash
docker-compose exec backend bash
ping 10.158.0.5
```

Check VPC network configuration.

### Issue: SSL certificate errors

**Fix:** Renew Let's Encrypt certificate:
```bash
certbot renew
docker-compose restart nginx
```

---

## 📝 Next Steps After Deployment

1. **Monitor for 24 hours** - Watch logs for errors
2. **Test all features** - Authentication, book upload, search, etc.
3. **Backup secrets** - Store JWT_SECRET_KEY and IP_SALT in secure vault
4. **Set up alerts** - Configure monitoring for errors/downtime
5. **Document any custom configs** - Update deployment docs
6. **Schedule secret rotation** - Plan to rotate in 90 days
7. **Security audit** - Review logs for suspicious activity

---

## 🔑 Secret Management

**Production Secrets Generated:**

✅ JWT_SECRET_KEY: `kT9wmB527ESH...` (64 chars)
✅ IP_SALT: `mL48xFB0spUf...` (32 chars)

**Important:**
- These are **different** from development secrets
- Never commit `.env` file to git
- Store in secure vault (1Password, Vault, etc.)
- Rotate every 90 days
- Use different secrets for dev/staging/prod

---

## 📞 Support

If you encounter issues:

1. Check logs: `docker-compose logs backend`
2. Verify `.env` values are filled in
3. Test connectivity to database/redis
4. Review [DEPLOYMENT_SECURITY.md](DEPLOYMENT_SECURITY.md)
5. Check [SECURITY_FIXES.md](SECURITY_FIXES.md)

**Emergency Contacts:**
- Infrastructure: [Your team contact]
- Security: [Your security contact]
- Database: [Your DBA contact]

---

## ✅ Deployment Complete!

Once all checks pass, your production deployment is secure and ready! 🎉

**Security Features Active:**
- ✅ HTTPS enforcement
- ✅ CORS protection
- ✅ Rate limiting
- ✅ JWT validation
- ✅ IP hashing (GDPR compliant)
- ✅ Security headers
- ✅ Error message sanitization

**Monitor regularly and rotate secrets quarterly for best security!**
