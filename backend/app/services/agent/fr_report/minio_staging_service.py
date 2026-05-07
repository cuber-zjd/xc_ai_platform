import json

from app.services.system.file_service import file_service


class MinIOStagingService:
    staging_root = "webroot/APP/reportlets_ai_staging"

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
        await file_service.upload_file(cpt_bytes, paths["cptObjectPath"], "application/octet-stream")
        await file_service.upload_file(
            json.dumps(dsl, ensure_ascii=False, indent=2).encode("utf-8"),
            paths["dslObjectPath"],
            "application/json",
        )
        await file_service.upload_file(query_sql.encode("utf-8"), paths["sqlObjectPath"], "text/plain")
        await file_service.upload_file(
            (create_table_sql or "").encode("utf-8"),
            paths["createSqlObjectPath"],
            "text/plain",
        )
        await file_service.upload_file(
            "\n".join(generation_log).encode("utf-8"),
            paths["logObjectPath"],
            "text/plain",
        )
        return paths


minio_staging_service = MinIOStagingService()
