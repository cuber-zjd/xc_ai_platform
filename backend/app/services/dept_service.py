import typing
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from app.models.system.sys_dept import SysDept
from app.models.system.sys_company import SysCompany
from app.schemas.dept import DeptTreeNode

class DeptService:
    @staticmethod
    async def get_tree(db: AsyncSession) -> typing.List[DeptTreeNode]:
        """
        构建组织架构树：公司 → 部门 → 子部门。
        公司作为顶层节点，部门通过 company_id 挂载到对应公司下，
        部门之间通过 parent_id 形成子树层级。
        """
        # 1. 加载所有公司
        company_query = select(SysCompany).where(SysCompany.is_deleted == 0).order_by(SysCompany.order)
        company_result = await db.exec(company_query)
        companies = company_result.all()

        # 2. 加载所有部门
        dept_query = select(SysDept).where(SysDept.is_deleted == 0).order_by(SysDept.order)
        dept_result = await db.exec(dept_query)
        depts = dept_result.all()

        # 3. 构建公司节点映射 (sync_id -> node)
        company_map: typing.Dict[str, DeptTreeNode] = {}
        for c in companies:
            node_id = c.sync_id or str(c.id)
            company_map[node_id] = DeptTreeNode(
                id=node_id,
                name=c.name,
                parent_id=c.parent_id,
                node_type="company"
            )

        # 4. 构建公司层级树（公司之间也有 parent_id）
        company_tree: typing.List[DeptTreeNode] = []
        for c in companies:
            node_id = c.sync_id or str(c.id)
            node = company_map[node_id]
            if c.parent_id and c.parent_id in company_map:
                company_map[c.parent_id].children.append(node)
            else:
                company_tree.append(node)

        # 5. 构建部门节点映射
        dept_map: typing.Dict[str, DeptTreeNode] = {}
        for d in depts:
            node_id = d.sync_id or str(d.id)
            dept_map[node_id] = DeptTreeNode(
                id=node_id,
                name=d.name,
                parent_id=d.parent_id,
                node_type="dept"
            )

        # 6. 挂载部门到公司下，或部门之间形成子树
        for d in depts:
            node_id = d.sync_id or str(d.id)
            node = dept_map[node_id]
            if d.parent_id and d.parent_id in dept_map:
                # 挂载到父部门下
                dept_map[d.parent_id].children.append(node)
            elif d.company_id and d.company_id in company_map:
                # 挂载到所属公司下
                company_map[d.company_id].children.append(node)
            else:
                # 无法归属，作为顶层（兜底）
                company_tree.append(node)

        return company_tree
