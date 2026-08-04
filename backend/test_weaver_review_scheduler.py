import unittest
from unittest.mock import AsyncMock, patch

from app.services.agent.weaver_ai_assistant.review_scheduler_service import (
    WeaverAiReviewSchedulerService,
)


class WeaverAiReviewSchedulerServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_run_once_aggregates_concurrent_candidate_results(self) -> None:
        service = WeaverAiReviewSchedulerService()
        candidates = [
            {"request_id": "1001", "node_id": "20"},
            {"request_id": "1002", "node_id": "20"},
            {"request_id": "1003", "node_id": "20"},
        ]
        service._load_enabled_node_configs = AsyncMock(return_value=[object()])
        service._scan_candidates = unittest.mock.Mock(return_value=candidates)
        service._claim = AsyncMock(side_effect=[101, None, 103])
        service._process_claimed_candidate = AsyncMock(
            side_effect=[
                {"status": "completed"},
                {
                    "status": "failed",
                    "requestId": "1003",
                    "nodeId": "20",
                    "message": "测试失败",
                },
            ]
        )

        with patch.object(service, "_batch_limit", return_value=10):
            result = await service.run_once()

        self.assertEqual(result["configuredNodes"], 1)
        self.assertEqual(result["discovered"], 3)
        self.assertEqual(result["completed"], 1)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["claimed"], 2)
        self.assertEqual(result["errors"][0]["requestId"], "1003")

    async def test_run_once_skips_reviewed_items_until_new_candidate_is_claimed(self) -> None:
        service = WeaverAiReviewSchedulerService()
        candidates = [
            {"request_id": "old-1", "node_id": "20"},
            {"request_id": "old-2", "node_id": "20"},
            {"request_id": "new-1", "node_id": "20"},
        ]
        service._load_enabled_node_configs = AsyncMock(return_value=[object()])
        service._scan_candidates = unittest.mock.Mock(return_value=candidates)
        service._claim = AsyncMock(side_effect=[None, None, 301])
        service._process_claimed_candidate = AsyncMock(return_value={"status": "completed"})

        with patch.object(service, "_batch_limit", return_value=1):
            result = await service.run_once()

        self.assertEqual(result["skipped"], 2)
        self.assertEqual(result["claimed"], 1)
        self.assertEqual(result["completed"], 1)
        service._process_claimed_candidate.assert_awaited_once_with(candidates[2], 301)

    async def test_run_once_does_not_scan_when_no_node_is_enabled(self) -> None:
        service = WeaverAiReviewSchedulerService()
        service._load_enabled_node_configs = AsyncMock(return_value=[])
        service._scan_candidates = unittest.mock.Mock(return_value=[])

        result = await service.run_once()

        self.assertEqual(result["configuredNodes"], 0)
        self.assertEqual(result["discovered"], 0)
        service._scan_candidates.assert_not_called()


if __name__ == "__main__":
    unittest.main()
