import json

from app.services.agent.fr_report.fr_minio_service import fr_minio_service


class MinIOStagingService:
    staging_root = "webroot/APP/reportlets/AI生成报表"

    async def save_artifacts(
        self,
        task_id: str,
        cpt_bytes: bytes,
        dsl: dict,
        query_sql: str,
        create_table_sql: str | None,
        generation_log: list[str],
    ) -> dict[str, str]:
        base_path = f"{self.staging_root}/{task_id}"
        paths = {
            "cptObjectPath": f"{base_path}/report.cpt",
            "dslObjectPath": f"{base_path}/report.dsl.json",
            "sqlObjectPath": f"{base_path}/query.sql",
            "createSqlObjectPath": f"{base_path}/create_table.sql",
            "logObjectPath": f"{base_path}/generation.log",
        }
        await fr_minio_service.upload_file(cpt_bytes, paths["cptObjectPath"], "application/octet-stream")
        await fr_minio_service.upload_file(
            json.dumps(dsl, ensure_ascii=False, indent=2).encode("utf-8"),
            paths["dslObjectPath"],
            "application/json",
        )
        await fr_minio_service.upload_file(query_sql.encode("utf-8"), paths["sqlObjectPath"], "text/plain")
        await fr_minio_service.upload_file(
            (create_table_sql or "").encode("utf-8"),
            paths["createSqlObjectPath"],
            "text/plain",
        )
        await fr_minio_service.upload_file(
            "\n".join(generation_log).encode("utf-8"),
            paths["logObjectPath"],
            "text/plain",
        )
        return paths

    async def save_ai_generated_report(
        self,
        snapshot_id: str,
        cpt_bytes: bytes,
        snapshot_payload: dict,
        operations: list[dict],
        generation_log: list[str],
    ) -> dict[str, str]:
        base_path = f"{self.staging_root}/快照/{snapshot_id}"
        paths = {
            "cptObjectPath": f"{base_path}/report.cpt",
            "metaObjectPath": f"{base_path}/snapshot.json",
            "operationsObjectPath": f"{base_path}/operations.json",
            "logObjectPath": f"{base_path}/generation.log",
        }
        await fr_minio_service.upload_file(cpt_bytes, paths["cptObjectPath"], "application/octet-stream")
        await fr_minio_service.upload_file(
            json.dumps(snapshot_payload, ensure_ascii=False, indent=2, default=str).encode("utf-8"),
            paths["metaObjectPath"],
            "application/json",
        )
        await fr_minio_service.upload_file(
            json.dumps(operations, ensure_ascii=False, indent=2, default=str).encode("utf-8"),
            paths["operationsObjectPath"],
            "application/json",
        )
        await fr_minio_service.upload_file(
            "\n".join(generation_log).encode("utf-8"),
            paths["logObjectPath"],
            "text/plain",
        )
        return paths


minio_staging_service = MinIOStagingService()
