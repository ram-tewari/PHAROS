#!/usr/bin/env python3
"""
Verify Render Free Tier Configuration

This script checks that all required configuration is in place
for deploying Pharos to Render Free tier.
"""

import os
import sys
from pathlib import Path

def check_file_exists(filepath: str, description: str) -> bool:
    """Check if a file exists."""
    if Path(filepath).exists():
        print(f"✅ {description}: {filepath}")
        return True
    else:
        print(f"❌ {description} NOT FOUND: {filepath}")
        return False

def check_render_yaml():
    """Verify render.yaml configuration."""
    print("\n📋 Checking render.yaml configuration...")
    
    yaml_path = "deployment/render.yaml"
    if not check_file_exists(yaml_path, "render.yaml"):
        return False
    
    with open(yaml_path, 'r') as f:
        content = f.read()
    
    checks = {
        "Service name": "pharos-cloud-api" in content,
        "Free tier plan": "plan: free" in content,
        "NeonDB connection": "neondb_owner" in content,
        "Upstash Redis URL": "living-sculpin-96916.upstash.io" in content,
        "Health check": "healthCheckPath: /health" in content,
        "Docker context": "dockerfilePath: ./deployment/Dockerfile.cloud" in content,
    }
    
    all_passed = True
    for check_name, passed in checks.items():
        if passed:
            print(f"  ✅ {check_name}")
        else:
            print(f"  ❌ {check_name}")
            all_passed = False
    
    return all_passed

def check_dockerfile():
    """Verify Dockerfile.cloud exists."""
    print("\n🐳 Checking Dockerfile.cloud...")
    return check_file_exists("deployment/Dockerfile.cloud", "Dockerfile.cloud")

def check_requirements():
    """Verify requirements files exist."""
    print("\n📦 Checking requirements files...")
    
    files = [
        ("requirements-base.txt", "Base requirements"),
        ("requirements-cloud.txt", "Cloud requirements"),
    ]
    
    all_exist = True
    for filename, description in files:
        if not check_file_exists(filename, description):
            all_exist = False
    
    return all_exist

def check_alembic():
    """Verify Alembic configuration."""
    print("\n🗄️ Checking Alembic configuration...")
    
    # Check for alembic.ini in config directory (correct location)
    alembic_ini_exists = False
    if Path("config/alembic.ini").exists():
        print(f"  ✅ Alembic config: config/alembic.ini")
        alembic_ini_exists = True
    elif Path("alembic.ini").exists():
        print(f"  ✅ Alembic config: alembic.ini")
        alembic_ini_exists = True
    else:
        print(f"  ❌ Alembic config NOT FOUND (checked: alembic.ini, config/alembic.ini)")
        alembic_ini_exists = False
    
    # Check for alembic/env.py
    env_exists = check_file_exists("alembic/env.py", "Alembic environment")
    
    return alembic_ini_exists and env_exists

def check_app_structure():
    """Verify app directory structure."""
    print("\n📁 Checking app structure...")
    
    dirs = [
        ("app", "App directory"),
        ("app/modules", "Modules directory"),
        ("app/shared", "Shared directory"),
    ]
    
    all_exist = True
    for dirname, description in dirs:
        if Path(dirname).is_dir():
            print(f"  ✅ {description}: {dirname}")
        else:
            print(f"  ❌ {description} NOT FOUND: {dirname}")
            all_exist = False
    
    return all_exist

def print_deployment_instructions():
    """Print next steps for deployment."""
    print("\n" + "="*60)
    print("🚀 DEPLOYMENT INSTRUCTIONS")
    print("="*60)
    print("""
1. Commit and push changes:
   git add backend/deployment/render.yaml
   git commit -m "Configure Render free tier deployment"
   git push origin main

2. Go to Render Dashboard:
   https://dashboard.render.com

3. Create New Web Service:
   - Click "New +" → "Web Service"
   - Connect GitHub repository
   - Select "pharos" repository
   - Render will auto-detect render.yaml

4. Verify Configuration:
   - Name: pharos-cloud-api
   - Region: Oregon
   - Branch: main
   - Plan: Free
   - Environment variables auto-populated

5. Deploy:
   - Click "Create Web Service"
   - Wait 10-15 minutes for build
   - Copy PHAROS_ADMIN_TOKEN from environment variables

6. Test Deployment:
   curl https://pharos-cloud-api.onrender.com/health

7. Set Up Keep-Alive (Optional):
   - Sign up at https://uptimerobot.com
   - Create HTTP(s) monitor
   - URL: https://pharos-cloud-api.onrender.com/health
   - Interval: 5 minutes

8. Configure Ronin:
   PHAROS_API_URL=https://pharos-cloud-api.onrender.com
   PHAROS_API_KEY=<YOUR_PHAROS_ADMIN_TOKEN>

📖 Full Guide: backend/RENDER_FREE_DEPLOYMENT.md
""")

def main():
    """Run all verification checks."""
    print("="*60)
    print("🔍 PHAROS RENDER FREE TIER CONFIGURATION VERIFICATION")
    print("="*60)
    
    # Change to backend directory
    backend_dir = Path(__file__).parent
    os.chdir(backend_dir)
    
    checks = [
        ("render.yaml", check_render_yaml),
        ("Dockerfile", check_dockerfile),
        ("Requirements", check_requirements),
        ("Alembic", check_alembic),
        ("App Structure", check_app_structure),
    ]
    
    results = {}
    for check_name, check_func in checks:
        results[check_name] = check_func()
    
    # Summary
    print("\n" + "="*60)
    print("📊 VERIFICATION SUMMARY")
    print("="*60)
    
    passed = sum(results.values())
    total = len(results)
    
    for check_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {check_name}")
    
    print(f"\nTotal: {passed}/{total} checks passed")
    
    if passed == total:
        print("\n✅ All checks passed! Ready to deploy to Render.")
        print_deployment_instructions()
        return 0
    else:
        print("\n❌ Some checks failed. Please fix the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
