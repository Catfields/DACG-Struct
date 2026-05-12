#!/usr/bin/env python3
"""
迁移脚本：更新现有用户的 login_flag 字段
- 有手机号的用户 -> login_flag = 3 (用户名+手机号)
- 无手机号的用户 -> login_flag = 1 (仅用户名)

执行方式：
    cd /data/home/zyx/Ir-UNet/DACG/DACG-Struct/backend
    python scripts/migrate_login_flag.py
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.config import settings


def migrate_login_flags():
    """Update login_flag for all users based on phone presence."""
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, future=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    db = SessionLocal()
    try:
        # Update users with phone -> login_flag = 3 (both username and phone)
        result_with_phone = db.execute(
            text("""
                UPDATE user 
                SET login_flag = 3 
                WHERE phone IS NOT NULL AND phone != ''
            """)
        )
        updated_with_phone = result_with_phone.rowcount
        
        # Update users without phone -> login_flag = 1 (username only)
        result_without_phone = db.execute(
            text("""
                UPDATE user 
                SET login_flag = 1 
                WHERE phone IS NULL OR phone = ''
            """)
        )
        updated_without_phone = result_without_phone.rowcount
        
        db.commit()
        
        print("✅ 迁移完成!")
        print(f"   - 有手机号的用户（设置为'用户名+手机号'）: {updated_with_phone} 条")
        print(f"   - 无手机号的用户（设置为'用户名'）: {updated_without_phone} 条")
        print(f"   - 总计更新: {updated_with_phone + updated_without_phone} 条")
        
        # Show sample data
        print("\n📊 更新后的用户登录方式分布:")
        result = db.execute(
            text("""
                SELECT login_flag, COUNT(*) as count 
                FROM user 
                GROUP BY login_flag
            """)
        )
        for row in result:
            flag = row[0]
            count = row[1]
            desc = {1: '用户名', 2: '手机号', 3: '用户名+手机号'}.get(flag, f'未知({flag})')
            print(f"   - {desc}: {count} 人")
        
        return True
        
    except Exception as e:
        db.rollback()
        print(f"❌ 迁移失败: {e}")
        return False
    finally:
        db.close()


if __name__ == "__main__":
    print("🚀 开始迁移用户登录方式...")
    print(f"   数据库: {settings.DATABASE_URL.replace('://', '://***:***@')}")
    print()
    
    success = migrate_login_flags()
    sys.exit(0 if success else 1)
