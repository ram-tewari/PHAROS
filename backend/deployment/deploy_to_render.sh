#!/bin/bash
# Pharos Render Free Tier Deployment Script
# Quick deployment helper for Render Free tier

set -e  # Exit on error

echo "============================================================"
echo "🚀 PHAROS RENDER FREE TIER DEPLOYMENT"
echo "============================================================"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Step 1: Verify configuration
echo "📋 Step 1: Verifying configuration..."
cd backend
python verify_render_config.py

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Configuration verification failed!${NC}"
    echo "Please fix the issues above and try again."
    exit 1
fi

echo -e "${GREEN}✅ Configuration verified!${NC}"
echo ""

# Step 2: Commit changes
echo "📝 Step 2: Committing changes..."
cd ..
git add backend/deployment/render.yaml
git add backend/deployment/Dockerfile.cloud
git add backend/RENDER_FREE_DEPLOYMENT.md
git add backend/RENDER_DEPLOYMENT_CHECKLIST.md
git add backend/UPTIMEROBOT_SETUP.md
git add backend/verify_render_config.py
git add backend/test_render_deployment.py
git add RENDER_DEPLOYMENT_SUMMARY.md

git commit -m "Configure Render free tier deployment with NeonDB and Upstash" || true

echo -e "${GREEN}✅ Changes committed!${NC}"
echo ""

# Step 3: Push to GitHub
echo "📤 Step 3: Pushing to GitHub..."
git push origin main

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Git push failed!${NC}"
    echo "Please check your Git configuration and try again."
    exit 1
fi

echo -e "${GREEN}✅ Pushed to GitHub!${NC}"
echo ""

# Step 4: Instructions for Render
echo "============================================================"
echo "🎯 NEXT STEPS: CREATE RENDER SERVICE"
echo "============================================================"
echo ""
echo "1. Go to Render Dashboard:"
echo "   ${YELLOW}https://dashboard.render.com${NC}"
echo ""
echo "2. Create New Web Service:"
echo "   - Click 'New +' → 'Web Service'"
echo "   - Connect your GitHub repository"
echo "   - Select 'pharos' repository"
echo "   - Render will auto-detect render.yaml"
echo ""
echo "3. Verify Configuration:"
echo "   - Name: pharos-cloud-api"
echo "   - Region: Oregon"
echo "   - Branch: main"
echo "   - Plan: Free"
echo ""
echo "4. Deploy:"
echo "   - Click 'Create Web Service'"
echo "   - Wait 10-15 minutes for build"
echo ""
echo "5. After Deployment:"
echo "   - Copy PHAROS_ADMIN_TOKEN from environment variables"
echo "   - Test health endpoint:"
echo "     ${YELLOW}curl https://pharos-cloud-api.onrender.com/health${NC}"
echo ""
echo "6. Set Up Keep-Alive (Recommended):"
echo "   - Sign up at ${YELLOW}https://uptimerobot.com${NC}"
echo "   - Create monitor for /health endpoint"
echo "   - See: backend/UPTIMEROBOT_SETUP.md"
echo ""
echo "7. Configure Ronin:"
echo "   ${YELLOW}PHAROS_API_URL=https://pharos-cloud-api.onrender.com${NC}"
echo "   ${YELLOW}PHAROS_API_KEY=<YOUR_PHAROS_ADMIN_TOKEN>${NC}"
echo ""
echo "============================================================"
echo "📖 DOCUMENTATION"
echo "============================================================"
echo ""
echo "- Full Guide: backend/RENDER_FREE_DEPLOYMENT.md"
echo "- Checklist: backend/RENDER_DEPLOYMENT_CHECKLIST.md"
echo "- Keep-Alive: backend/UPTIMEROBOT_SETUP.md"
echo "- Summary: RENDER_DEPLOYMENT_SUMMARY.md"
echo ""
echo "============================================================"
echo "✅ READY TO DEPLOY!"
echo "============================================================"
echo ""
echo "Your changes have been pushed to GitHub."
echo "Now go to Render Dashboard and create the web service."
echo ""
echo -e "${GREEN}Good luck! 🚀${NC}"
