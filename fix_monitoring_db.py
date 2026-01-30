#!/usr/bin/env python3
"""
Fix monitoring router to use sync database sessions
"""

def fix_monitoring_router():
    router_file = "/mnt/c/Users/rooma/PycharmProjects/neo_alexadria/backend/app/modules/monitoring/router.py"
    
    with open(router_file, 'r') as f:
        content = f.read()
    
    # Replace imports and dependencies
    content = content.replace(
        "from ...shared.database import get_db",
        "from ...shared.database import get_sync_db"
    )
    
    content = content.replace(
        "Depends(get_db)",
        "Depends(get_sync_db)"
    )
    
    with open(router_file, 'w') as f:
        f.write(content)
    
    print("✅ Fixed monitoring router to use sync database sessions")

if __name__ == "__main__":
    fix_monitoring_router()
