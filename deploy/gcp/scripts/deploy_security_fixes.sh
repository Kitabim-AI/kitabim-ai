#!/bin/bash
# ============================================================
# Production Deployment Script - Security Fixes
# ============================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Kitabim.AI - Production Deployment${NC}"
echo -e "${BLUE}Security Fixes - $(date)${NC}"
echo -e "${BLUE}========================================${NC}"
echo

# Check we're in the right directory
if [ ! -f "docker-compose.yml" ]; then
    echo -e "${RED}Error: Must run from deploy/gcp directory${NC}"
    exit 1
fi

# Check .env file exists
if [ ! -f ".env" ]; then
    echo -e "${RED}Error: .env file not found${NC}"
    echo -e "${YELLOW}Please copy .env.template to .env and fill in values${NC}"
    exit 1
fi

# Check for FILL_IN values
if grep -q "FILL_IN" .env; then
    echo -e "${RED}Error: .env file contains FILL_IN placeholders${NC}"
    echo -e "${YELLOW}Please update all FILL_IN values in .env${NC}"
    grep "FILL_IN" .env
    exit 1
fi

# Verify critical environment variables
echo -e "${BLUE}Checking environment variables...${NC}"
source .env

if [ -z "$JWT_SECRET_KEY" ] || [ ${#JWT_SECRET_KEY} -lt 32 ]; then
    echo -e "${RED}Error: JWT_SECRET_KEY missing or too short${NC}"
    exit 1
fi
echo -e "${GREEN}✓ JWT_SECRET_KEY configured (${#JWT_SECRET_KEY} chars)${NC}"

if [ -z "$IP_SALT" ] || [ ${#IP_SALT} -lt 16 ]; then
    echo -e "${RED}Error: IP_SALT missing or too short${NC}"
    exit 1
fi
echo -e "${GREEN}✓ IP_SALT configured (${#IP_SALT} chars)${NC}"

if [ "$ENVIRONMENT" != "production" ]; then
    echo -e "${RED}Error: ENVIRONMENT must be 'production'${NC}"
    exit 1
fi
echo -e "${GREEN}✓ ENVIRONMENT set to production${NC}"

if [ -z "$CORS_ORIGINS" ] || [ "$CORS_ORIGINS" == "*" ]; then
    echo -e "${RED}Error: CORS_ORIGINS must be set to specific origins${NC}"
    exit 1
fi
echo -e "${GREEN}✓ CORS_ORIGINS configured: $CORS_ORIGINS${NC}"

echo

# Ask for confirmation
echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}Ready to deploy to PRODUCTION${NC}"
echo -e "${YELLOW}========================================${NC}"
echo
echo "Registry: ${REGISTRY}"
echo "Image Tag: ${IMAGE_TAG}"
echo "CORS Origins: ${CORS_ORIGINS}"
echo
read -p "Continue with deployment? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo -e "${RED}Deployment cancelled${NC}"
    exit 0
fi

echo
echo -e "${BLUE}Pulling latest images...${NC}"
docker-compose pull

echo
echo -e "${BLUE}Stopping existing containers...${NC}"
docker-compose down

echo
echo -e "${BLUE}Starting containers with new configuration...${NC}"
docker-compose up -d

echo
echo -e "${BLUE}Waiting for services to start...${NC}"
sleep 10

echo
echo -e "${BLUE}Checking service health...${NC}"

# Wait for backend to be ready
max_attempts=30
attempt=0
while [ $attempt -lt $max_attempts ]; do
    if docker-compose exec -T backend curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Backend is healthy${NC}"
        break
    fi
    attempt=$((attempt + 1))
    echo -n "."
    sleep 2
done

if [ $attempt -eq $max_attempts ]; then
    echo -e "${RED}Error: Backend failed to start${NC}"
    echo -e "${YELLOW}Check logs with: docker-compose logs backend${NC}"
    exit 1
fi

echo
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Deployment Complete! ✓${NC}"
echo -e "${BLUE}========================================${NC}"
echo
echo -e "${GREEN}✓ All services running${NC}"
echo -e "${GREEN}✓ Security fixes applied${NC}"
echo -e "${GREEN}✓ Production configuration active${NC}"
echo
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Verify HTTPS: curl -I https://kitabim.ai/api/health"
echo "2. Check security headers in response"
echo "3. Test authentication flow"
echo "4. Monitor logs: docker-compose logs -f"
echo
echo -e "${BLUE}For detailed verification steps, see:${NC}"
echo "  deploy/gcp/PRODUCTION_DEPLOYMENT.md"
echo
