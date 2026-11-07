from app.services.agent.insight.crawler.body_quality import assess_body


def test_preserves_short_factual_news():
    text = "国务院公布食品产业发展政策，涉及质量管理和产业扶持。" * 12
    cleaned, quality = assess_body(text, "国务院公布食品产业发展政策")
    assert cleaned == text
    assert quality["status"] == "passed_rules"


def test_duplicate_and_ui_preserve_original_evidence():
    paragraph = "玉米深加工企业发布新增生产线建设公告，介绍产能、生产工艺及后续采购安排。" * 5
    original = f"首页\n{paragraph}\n{paragraph}\n联系我们"
    cleaned, quality = assess_body(original, "玉米深加工生产线建设")
    assert cleaned == paragraph
    assert len(quality["removed"]) == 3
    assert quality["original_chars"] == len(original)


def test_reference_and_video_not_deleted():
    for title, body in [("谷神公司 - 企查查", "企业信息" * 100),
                        ("玉米加工项目", "打开今日头条查看完整视频\n" + "玉米加工项目" * 60)]:
        cleaned, quality = assess_body(body, title)
        assert cleaned
        assert quality["status"] == "needs_review"


def test_link_dense_and_title_mismatch_flagged():
    body = "\n".join(f"[其他资讯{i}](https://example.org/{i})" for i in range(30))
    cleaned, quality = assess_body(body, "玉米糖浆工厂正式投产")
    assert cleaned == body
    assert quality["status"] == "needs_review"
    assert len(quality["issues"]) >= 2
