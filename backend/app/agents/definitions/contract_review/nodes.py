import asyncio
from typing import Dict, List
from langchain_core.messages import SystemMessage, HumanMessage
from app.core.llm_factory import LLMFactory
from app.agents.definitions.contract_review.state import ReviewState, AuditFinding
from app.services.file_service import file_service
from app.services.rule_service import rule_service
from app.core.logger import logger
import io

# Optional imports for document handling
try:
    import docx
    from pypdf import PdfReader
except ImportError:
    pass

async def loader_node(state: ReviewState) -> Dict:
    """
    Downloads file from MinIO and extracts text.
    """
    logger.info(f"Loader Node: Processing {state['file_path']}")
    file_bytes = await file_service.download_file(state['file_path'])
    
    text = ""
    file_ext = state['file_path'].split('.')[-1].lower()
    
    try:
        if file_ext == "docx":
            doc = docx.Document(io.BytesIO(file_bytes))
            text = "\n".join([p.text for p in doc.paragraphs])
        elif file_ext == "pdf":
            reader = PdfReader(io.BytesIO(file_bytes))
            text = "\n".join([page.extract_text() for page in reader.pages])
        else:
            # Fallback to plain text
            text = file_bytes.decode('utf-8', errors='ignore')
    except Exception as e:
        logger.error(f"Text extraction failed: {e}")
        text = "Error extracting text. AI analysis may be limited."
        
    return {"text_content": text}

async def rule_check_node(state: ReviewState) -> Dict:
    """
    Checks against DB rules using simple Keyword/Regex matching.
    """
    logger.info("Rule Check Node")
    # In a real system, we'd inject session dependency or use a scoped session
    # For now, we mock or assume rules are fetched via a helper that manages session
    # risks = await rule_service.apply_rules(state['text_content'], state['contract_type'])
    
    # Mock finding for demo
    findings = []
    text = state.get("text_content", "")
    
    if "付款" in text and "违约金" not in text:
         findings.append(AuditFinding(
             summary="缺少违约金条款",
             detail="合同中包含付款义务，但未发现‘违约金’相关表述，存在风险。",
             risk_level="warning"
         ))

    return {"rule_findings": findings}

async def llm_audit_node(state: ReviewState) -> Dict:
    """
    Uses LLM to find subtle risks.
    """
    logger.info("LLM Audit Node")
    llm = LLMFactory.get_model(temperature=0.1, json_mode=False) # Keep json_mode False for now unless we structure prompt perfectly
    
    prompt = f"""
    作为一名资深法务，请审查以下合同文本。
    合同类型: {state['contract_type']}
    
    主要任务：
    1. 找出对甲方明显不利的隐藏条款。
    2. 检查是否有管辖权陷阱。
    3. 语言是否清晰，有无歧义。
    
    合同文本：
    {state['text_content'][:4000]} (Truncated for demo)
    
    请列出风险点，格式如下：
    - 风险等级(Critical/Warning/Info): [标题] - [详细说明]
    """
    
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    content = response.content
    
    # Parse generic response to findings (Simple parsing)
    findings = []
    for line in content.split('\n'):
        if "Critical" in line or "Warning" in line:
            level = "critical" if "Critical" in line else "warning"
            findings.append(AuditFinding(
                summary="AI 智能发现",
                detail=line.strip(),
                risk_level=level
            ))
            
    return {"llm_findings": findings}

async def synthesizer_node(state: ReviewState) -> Dict:
    """
    Merges findings and decides traffic light.
    """
    all_risks = state.get("rule_findings", []) + state.get("llm_findings", [])
    
    critical_count = sum(1 for r in all_risks if r.risk_level.lower() == "critical")
    warning_count = sum(1 for r in all_risks if r.risk_level.lower() == "warning")
    
    traffic_light = "green"
    if critical_count > 0:
        traffic_light = "red"
    elif warning_count > 0:
        traffic_light = "yellow"
        
    summary = {
        "total_risks": len(all_risks),
        "critical": critical_count,
        "warning": warning_count,
        "score": max(0, 100 - critical_count * 20 - warning_count * 5)
    }
    
    # Convert AuditFinding objects to dicts for JSON serialization
    serialized_findings = [f.dict() for f in all_risks]
    
    # Update Contract in DB? 
    # Ideally, the graph returns result and Service updates DB.
    
    return {
        "traffic_light": traffic_light,
        "analysis_summary": summary,
        # We can store identifying info in state to pass back
    }
