# SAP AI RFC 示例说明

本目录提供 SAP ECC 侧的第一版 RFC 示例代码。目标是让 AI 平台不直连数据库，而是通过 SAP 内部只读 RFC 获取代码、DDIC、日志和少量分页数据。

## 部署建议

1. 在 SE80 或 SE37 创建函数组，例如 `ZFG_AI_ASSISTANT`。函数组主程序 `SAPLZFG_AI_ASSISTANT` 第一行必须是 `FUNCTION-POOL ZFG_AI_ASSISTANT.`。
2. 不要把本目录的 `ZFM_AI_*.abap` 粘到函数组主程序 `SAPLZFG_AI_ASSISTANT`，也不要粘到 TOP include。它们是单个函数模块的源码区内容。
3. 按文件名创建 RFC 函数模块，并在 SE37 的“属性”页签勾选远程启用模块；先维护“导入/表”页签接口，再把对应 `.abap` 内容复制到该函数模块的源码区。
4. 先创建或替换 `ZFM_AI_PING`，用平台的 `/api/v1/sap/systems/{id}/test-connection` 验证连通性。
5. 再逐个创建源码、DDIC、ZILOG 和只读分页数据读取函数。
6. 生产系统只传输经过审批的只读函数模块和审计配置。

如果激活时报 `SAPLZFG_AI_ASSISTANT` 缺少 `REPORT/PROGRAM` 或 program type is INCLUDE，通常说明函数组主程序没有正确生成或第一行缺少 `FUNCTION-POOL ZFG_AI_ASSISTANT.`。处理方式是回到函数组主程序补上这一行，或删除错误对象后重新用 SE80/SE37 创建函数组。

## 函数短文本建议

| 函数模块 | 短文本 |
| --- | --- |
| `ZFM_AI_PING` | AI 平台 SAP RFC 连接测试 |
| `ZFM_AI_GET_TCODE_INFO` | AI 查询事务码和描述候选 |
| `ZFM_AI_GET_PROGRAM_SOURCE` | AI 读取程序或函数完整源码 |
| `ZFM_AI_GET_DDIC_META` | AI 查询 DDIC 表和结构元数据 |
| `ZFM_AI_QUERY_ZILOG` | AI 查询 ZILOG 函数日志 |
| `ZFM_AI_READ_TABLE_SAFE` | AI 只读分页读取表数据 |

## RFC 接口类型约定

- ECC/classic RFC 里不要把函数模块接口直接定义为 `TYPE STRING`。
- SE37 函数接口不能引用函数组 TOP include 里的本地 `TYPES`，需要先在 SE11 创建全局结构。
- 示例统一使用 `ET_JSON_LINES STRUCTURE ZSAI_JSON_LINE` 返回 JSON 分片，每行 `CHAR255`。
- 平台侧会把 `ET_JSON_LINES-LINE` 拼接成 `JSON_TEXT` 再解析或展示。
- 函数内部局部变量可以用 `string` 拼 JSON；RFC Importing/Exporting/Tables 接口尽量使用 DDIC 基本类型、`CHAR` 和扁平结构。

## 需要先建的 SE11 结构

### ZSAI_JSON_LINE

| 字段 | 类型 | 长度 | 说明 |
| --- | --- | --- | --- |
| `LINE` | `CHAR` | `255` | JSON 分片内容 |

### ZSAI_RANGE

| 字段 | 类型 | 长度 | 说明 |
| --- | --- | --- | --- |
| `FIELDNAME` | `FIELDNAME` | - | 字段名 |
| `SIGN` | `DDSIGN` | - | I/E |
| `OPTION` | `DDOPTION` | - | EQ/BT/CP 等 |
| `LOW` | `CHAR` | `255` | 条件低值 |
| `HIGH` | `CHAR` | `255` | 条件高值 |

### ZSAI_FIELD_NAME

| 字段 | 类型 | 长度 | 说明 |
| --- | --- | --- | --- |
| `FIELDNAME` | `FIELDNAME` | - | 需要返回的字段名 |

## 返回量与 token 控制

- 只读工具默认不做 Z/Y 或标准对象限制，但必须限制返回量。
- 源码读取默认 `IV_MAX_LINES = 0`，表示 SAP 侧一次完整拉取源码；平台侧再按片段压缩投喂给 AI。
- 如需临时只读部分源码，可传 `IV_START_LINE` 和 `IV_MAX_LINES`，后端工具参数最大允许 `5000` 行。
- 读取函数模块源码时，`ZFM_AI_GET_PROGRAM_SOURCE` 会优先用 `FUNCTION_INCLUDE_INFO` 解析函数对应的具体实现 include，例如 `L<函数组>U01`；不要只读取 `SAPL<函数组>`，它通常只是函数池框架。
- 日志默认 `60` 行，最大建议不超过 `120` 行。
- 数据样例默认 `80` 行，最大建议不超过 `200` 行。
- 表数据返回使用 `fields` 字段数组 + `rows` 行数组，减少每行重复字段名带来的 token 消耗。
- 平台侧会压缩给 LLM 的证据 JSON，跳过原始 `ET_JSON_LINES`，截断超长文本，并提示可继续调用工具获取后续内容。

## 安全原则

- 不开放任意 SQL。
- 所有工具只读，不做写入、删除、提交或修改。
- `ZFM_AI_READ_TABLE_SAFE` 默认最大返回 80 行，示例最大限制 200 行。
- WHERE 条件使用结构化 ranges，由 RFC 内部转换，禁止把 AI 生成的 SQL 字符串直接传入 SAP 执行。
- 所有 RFC 建议写调用审计日志，至少记录用户、时间、函数名、对象名、行数和执行结果。

## 需要你按现场调整

- `ZFM_AI_QUERY_ZILOG.abap` 中的日志表名、字段名需要替换为你们真实 ZILOG 结构。
- `ZFM_AI_READ_TABLE_NOTES.abap` 是只读审计和返回量控制建议，需要时可用 SE11 创建透明表或维护视图。
- 如果你们已有统一权限对象，可把示例里的 `AUTHORITY-CHECK` 替换为企业标准权限对象。
- 如果 ECC 版本没有 `/UI2/CL_JSON`，需要换成你们系统已有 JSON 工具类，或返回 RFC TABLE 参数。

## 平台侧环境变量

管理页面只保存环境变量名，不保存密码。例如：

```powershell
SAP_PRD_800_USER=AI_RFC_USER
SAP_PRD_800_PASSWORD=********
```

对应 SAP 系统配置中填写：

- 用户环境变量：`SAP_PRD_800_USER`
- 密码环境变量：`SAP_PRD_800_PASSWORD`
