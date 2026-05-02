from typing import List, Dict, Any
import pyodbc
import logging
from datetime import datetime
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from app.models.system.sys_user import SysUser
from app.models.system.sys_company import SysCompany
from app.models.system.sys_dept import SysDept
from app.models.system.sys_post import SysPost
from app.db.session import engine, async_session 

# Configure logger
logger = logging.getLogger(__name__)

# SQL Server Config
MSSQL_HOST = "192.168.14.127"
MSSQL_USER = "sa"
MSSQL_PASS = "Xckg123456!"
MSSQL_DB = "ehr"

class HrSyncService:
    @staticmethod
    def get_mssql_connection():
        # Using "SQL Server" driver as confirmed by check_db.py
        conn_str = (
            "DRIVER={SQL Server};"
            f"SERVER={MSSQL_HOST};"
            f"DATABASE={MSSQL_DB};"
            f"UID={MSSQL_USER};"
            f"PWD={MSSQL_PASS};"
            "TrustServerCertificate=yes;"
        )
        return pyodbc.connect(conn_str)

    @staticmethod
    def map_gender(val: Any) -> str:
        # Assuming source is Chinese or specific code. Adjust based on real data.
        # Screenshot doesn't show values, defaulting to string copy or basic normalization
        if not val:
            return None
        s = str(val).strip()
        if s == "男" or s == "M" or s == "0":
            return "Male"
        if s == "女" or s == "F" or s == "1":
            return "Female"
        return s

    @staticmethod
    def map_employment_status(val: Any) -> tuple[int, str]:
        """
        Maps HR status string to (status_code, status_desc).
        0: 试用, 1: 正式, 2: 临时, 3: 试用延期, 4: 解聘, 5: 离职, 6: 退休, 7: 其他
        """
        if not val:
            return (7, "其他")
        
        s = str(val).strip()
        desc = s
        
        if s == '试用': return (0, s)
        if s == '正式': return (1, s)
        if s == '临时': return (2, s)
        if s == '试用延期': return (3, s)
        if s == '解聘': return (4, s)
        if s == '离职': return (5, s)
        if s == '退休': return (6, s)
        
        return (7, s) # Default to Other

    @staticmethod
    def map_is_deleted(status_code: int) -> int:
        """
        Derive is_deleted from status_code.
        4(解聘), 5(离职), 6(退休) -> Deleted (1)
        Others -> Active (0)
        """
        if status_code in [4, 5, 6]:
            return 1
        return 0

    @staticmethod
    def map_common_status(val: Any) -> int:
        """
        For Company/Dept/Post which likely satisfy standard deleted=0/1 logic?
        User didn't specify. Assuming standard: 1=Deleted? Or 0=Deleted?
        Previous code: 1(Deleted) -> 0(Status=Disabled?), 0(Active) -> 1(Status=Normal).
        BaseDBModel: is_deleted: 0=Active, 1=Deleted.
        So if source is 1 (Deleted), is_deleted=1.
        """
        try:
            return int(val)
        except:
            return 0 # Default Not Deleted

    @staticmethod
    async def sync_companies():
        logger.info("Starting HR Company Sync...")
        data = []
        try:
            conn = HrSyncService.get_mssql_connection()
            cursor = conn.cursor()
            query = """
            SELECT 
                companyid as sync_id,
                companyname as name,
                companycode as code,
                parentid as parent_id,
                orderindex as order_index,
                deleted as deleted_flag
            FROM ZView_FanWei_Company
            """
            cursor.execute(query)
            columns = [column[0] for column in cursor.description]
            data = [dict(zip(columns, row)) for row in cursor.fetchall()]
            conn.close()
        except Exception as e:
            logger.error(f"Failed to fetch Companies: {e}")
            return # Don't raise, try next

        async with AsyncSession(engine) as session:
            for row in data:
                try:
                    sync_id = str(row['sync_id']) if row['sync_id'] else None
                    if not sync_id: continue
                    
                    statement = select(SysCompany).where(SysCompany.sync_id == sync_id)
                    result = await session.exec(statement)
                    obj = result.first()
                    
                    if not obj:
                        obj = SysCompany(sync_id=sync_id, create_by="system_sync")
                    
                    obj.name = str(row['name']) if row['name'] else "Unknown"
                    obj.code = str(row['code']) if row['code'] else None
                    obj.parent_id = str(row['parent_id']) if row['parent_id'] else None
                    try:
                        obj.order = int(row['order_index']) if row['order_index'] else 0
                    except:
                        obj.order = 0
                    
                    obj.is_deleted = HrSyncService.map_common_status(row['deleted_flag'])
                    obj.update_time = datetime.now()
                    obj.update_by = "system_sync"
                    session.add(obj)
                except Exception as e:
                    logger.error(f"Error syncing company {row.get('sync_id')}: {e}")
            await session.commit()
            logger.info("Company Sync Completed.")

    @staticmethod
    async def sync_depts():
        logger.info("Starting HR Dept Sync...")
        data = []
        try:
            conn = HrSyncService.get_mssql_connection()
            cursor = conn.cursor()
            # Image shows 'detpname' (typo in source DB likely), I must use what IS in the source.
            query = """
            SELECT 
                deptid as sync_id,
                detpname as name,
                dept_code as code,
                parentid as parent_id,
                rootparentid as company_id,
                orderindex as order_index,
                deleted as deleted_flag
            FROM ZView_FanWei_Department
            """
            cursor.execute(query)
            columns = [column[0] for column in cursor.description]
            data = [dict(zip(columns, row)) for row in cursor.fetchall()]
            conn.close()
        except Exception as e:
            logger.error(f"Failed to fetch Depts: {e}")
            return

        async with AsyncSession(engine) as session:
            for row in data:
                try:
                    sync_id = str(row['sync_id']) if row['sync_id'] else None
                    if not sync_id: continue
                    
                    statement = select(SysDept).where(SysDept.sync_id == sync_id)
                    result = await session.exec(statement)
                    obj = result.first()
                    
                    if not obj:
                        obj = SysDept(sync_id=sync_id, create_by="system_sync")
                    
                    obj.name = str(row['name']) if row['name'] else "Unknown"
                    obj.code = str(row['code']) if row['code'] else None
                    obj.parent_id = str(row['parent_id']) if row['parent_id'] else None
                    obj.company_id = str(row['company_id']) if row['company_id'] else None
                    try:
                        obj.order = int(row['order_index']) if row['order_index'] else 0
                    except:
                        obj.order = 0
                    
                    obj.is_deleted = HrSyncService.map_common_status(row['deleted_flag'])
                    obj.update_time = datetime.now()
                    obj.update_by = "system_sync"
                    session.add(obj)
                except Exception as e:
                    logger.error(f"Error syncing dept {row.get('sync_id')}: {e}")
            await session.commit()
            logger.info("Dept Sync Completed.")

    @staticmethod
    async def sync_posts():
        logger.info("Starting HR Post Sync...")
        data = []
        try:
            conn = HrSyncService.get_mssql_connection()
            cursor = conn.cursor()
            query = """
            SELECT 
                postno as sync_id,
                postname as name,
                postno as code,
                dept_id as dept_id,
                deleted as deleted_flag
            FROM ZView_FanWei_Post
            """
            cursor.execute(query)
            columns = [column[0] for column in cursor.description]
            data = [dict(zip(columns, row)) for row in cursor.fetchall()]
            conn.close()
        except Exception as e:
            logger.error(f"Failed to fetch Posts: {e}")
            return

        async with AsyncSession(engine) as session:
            for row in data:
                try:
                    sync_id = str(row['sync_id']) if row['sync_id'] else None
                    if not sync_id: continue
                    
                    statement = select(SysPost).where(SysPost.sync_id == sync_id)
                    result = await session.exec(statement)
                    obj = result.first()
                    
                    if not obj:
                        obj = SysPost(sync_id=sync_id, create_by="system_sync")
                    
                    obj.name = str(row['name']) if row['name'] else "Unknown"
                    obj.code = str(row['code']) if row['code'] else None
                    obj.dept_id = str(row['dept_id']) if row['dept_id'] else None
                    
                    obj.is_deleted = HrSyncService.map_common_status(row['deleted_flag'])
                    obj.update_time = datetime.now()
                    obj.update_by = "system_sync"
                    session.add(obj)
                except Exception as e:
                    logger.error(f"Error syncing post {row.get('sync_id')}: {e}")
            await session.commit()
            logger.info("Post Sync Completed.")

    @staticmethod
    async def sync_all():
        await HrSyncService.sync_companies()
        await HrSyncService.sync_depts()
        await HrSyncService.sync_posts()
        await HrSyncService.sync_users()

    @staticmethod
    async def sync_users():
        logger.info("Starting HR User Sync...")
        
        # 1. Fetch from SQL Server (Blocking, but okay for script)
        users_data = []
        try:
            # PyODBC connection
            conn = HrSyncService.get_mssql_connection()
            cursor = conn.cursor()
            
            # Select fields matching the mapping
            query = """
            SELECT 
                a0188 as sync_id,
                a0190 as username,
                a0101 as full_name,
                a0107 as gender,
                a0121 as ethnicity,
                a0177 as id_card,
                a01274 as mobile,
                a01085 as education,
                deptid as dept_id,
                j01_e0101 as job_title,
                user_pre as supervisor_id,
                deleted as deleted_flag,
                a0144 as hire_date,
                a01107 as contract_start_date,
                a01108 as contract_end_date,
                a01003 as level,
                a0190 as employee_id,
                a01004 as travel_level,
                a0111 as birth_date,
                a01004order as job_order
            FROM ZView_FanWei_User_All
            """
            cursor.execute(query)
            
            # Convert rows to dicts
            columns = [column[0] for column in cursor.description]
            users_data = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            logger.info(f"Fetched {len(users_data)} users from SQL Server.")
            
            conn.close()
        except Exception as e:
            logger.error(f"Failed to connect or fetch from SQL Server: {e}")
            raise e

        # 2. Sync to Postgres (Async)
        async with AsyncSession(engine) as session:
            for row in users_data:
                try:
                    sync_id = str(row['sync_id']) if row['sync_id'] else None
                    if not sync_id:
                        continue # Skip invalid rows
                    
                    # Check existing
                    statement = select(SysUser).where(SysUser.sync_id == sync_id)
                    result = await session.exec(statement)
                    existing_user = result.first()
                    
                    if not existing_user:
                        existing_user = SysUser()
                        existing_user.create_by = "system_sync"
                    
                    # Update fields
                    existing_user.sync_id = sync_id
                    existing_user.username = str(row['username']) if row['username'] else f"u_{sync_id}"
                    existing_user.full_name = str(row['full_name']) if row['full_name'] else "Unknown"
                    existing_user.gender = HrSyncService.map_gender(row['gender'])
                    existing_user.ethnicity = str(row['ethnicity']) if row['ethnicity'] else None
                    existing_user.id_card = str(row['id_card']) if row['id_card'] else None
                    existing_user.mobile = str(row['mobile']) if row['mobile'] else None
                    existing_user.education = str(row['education']) if row['education'] else None
                    existing_user.dept_id = str(row['dept_id']) if row['dept_id'] else None
                    existing_user.job_title = str(row['job_title']) if row['job_title'] else None
                    existing_user.supervisor_id = str(row['supervisor_id']) if row['supervisor_id'] else None
                    
                    # Date handling (might be datetime or date object from driver, or string)
                    existing_user.hire_date = str(row['hire_date']) if row['hire_date'] else None
                    existing_user.contract_start_date = str(row['contract_start_date']) if row['contract_start_date'] else None
                    existing_user.contract_end_date = str(row['contract_end_date']) if row['contract_end_date'] else None
                    existing_user.birth_date = str(row['birth_date']) if row['birth_date'] else None
                    
                    existing_user.level = str(row['level']) if row['level'] else None
                    existing_user.employee_id = str(row['employee_id']) if row['employee_id'] else None
                    existing_user.travel_level = str(row['travel_level']) if row['travel_level'] else None
                    existing_user.job_order = str(row['job_order']) if row['job_order'] else None
                    
                    existing_user.job_order = str(row['job_order']) if row['job_order'] else None
                    
                    # Status Mapping
                    # Source 'deleted_flag' contains text like '正式', '离职' per user info
                    hr_status_text = row['deleted_flag']
                    status_code, status_desc = HrSyncService.map_employment_status(hr_status_text)
                    
                    existing_user.status = status_code
                    existing_user.status_desc = status_desc
                    existing_user.is_deleted = HrSyncService.map_is_deleted(status_code)
                    
                    existing_user.update_time = datetime.now()
                    existing_user.update_by = "system_sync"
                    
                    session.add(existing_user)
                except Exception as row_err:
                    logger.error(f"Error processing user {row.get('username', 'unknown')}: {row_err}")
                    continue
            
            await session.commit()
            logger.info("Sync completed successfully.")

if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    asyncio.run(HrSyncService.sync_users())
