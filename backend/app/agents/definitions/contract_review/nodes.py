import asyncio
from typing import Dict, List
from langchain_core.messages import SystemMessage, HumanMessage
from app.core.llm_factory import LLMFactory
from app.agents.definitions.contract_review.state import ReviewState, AuditFinding
from app.services.system.file_service import file_service
from app.services.agent.contract.rule_service import rule_service
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
    Supports: .docx, .doc, .pdf, .txt
    """
    logger.info(f"Loader Node: Processing {state['file_path']}")
    file_bytes = await file_service.download_file(state['file_path'])
    
    text = ""
    file_ext = state['file_path'].split('.')[-1].lower()
    
    try:
        if file_ext == "docx":
            doc = docx.Document(io.BytesIO(file_bytes))
            text = "\n".join([p.text for p in doc.paragraphs])
        elif file_ext == "doc":
            # 处理旧版 .doc 格式
            # 方法1: 尝试使用 python-docx2txt（支持部分 .doc）
            try:
                import docx2txt
                import tempfile
                import os
                # 需要先写入临时文件
                with tempfile.NamedTemporaryFile(delete=False, suffix='.doc') as tmp:
                    tmp.write(file_bytes)
                    tmp_path = tmp.name
                text = docx2txt.process(tmp_path)
                os.unlink(tmp_path)
            except ImportError:
                logger.warning("docx2txt not installed, trying alternative method")
                # 方法2: 尝试使用 mammoth（可以处理部分 doc 文件）
                try:
                    import mammoth
                    result = mammoth.extract_raw_text(io.BytesIO(file_bytes))
                    text = result.value
                except ImportError:
                    logger.warning("mammoth not installed, trying basic extraction")
                    # 方法3: 作为二进制文本提取（可能包含乱码但能获取部分文本）
                    import re
                    raw_text = file_bytes.decode('latin-1', errors='ignore')
                    # 尝试提取可读文本
                    text = re.sub(r'[^\x20-\x7E\u4e00-\u9fff\n]', '', raw_text)
                except Exception as e:
                    logger.error(f"Mammoth extraction failed: {e}")
                    text = "Error: Unable to extract text from .doc file. Please convert to .docx format."
            except Exception as e:
                logger.error(f"docx2txt extraction failed: {e}")
                text = "Error: Unable to extract text from .doc file. Please convert to .docx format."
        elif file_ext == "pdf":
            reader = PdfReader(io.BytesIO(file_bytes))
            text = "\n".join([page.extract_text() for page in reader.pages])
        elif file_ext == "txt":
            # 尝试多种编码
            for encoding in ['utf-8', 'gbk', 'gb2312', 'latin-1']:
                try:
                    text = file_bytes.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
        else:
            # Fallback to plain text
            text = file_bytes.decode('utf-8', errors='ignore')
            
        # 记录提取结果
        if text:
            logger.info(f"Text extraction successful: {len(text)} characters")
        else:
            logger.warning("No text extracted from document")
            
    except Exception as e:
        logger.error(f"Text extraction failed: {e}")
        text = f"Error extracting text: {str(e)}. AI analysis may be limited."
        
    return {"text_content": text}

async def rule_check_node(state: ReviewState) -> Dict:
    """
    Checks against DB rules using simple Keyword/Regex matching.
    """
    logger.info("Rule Check Node")
    
    findings = []
    text = state.get("text_content", "")
    
    # 辅助函数：提取包含关键词的完整句子作为 quote
    def extract_quote(keyword: str, context_text: str) -> str:
        """从文本中提取包含关键词的完整句子"""
        # 按句号、分号、换行符分割句子
        import re
        sentences = re.split(r'[。；\n]', context_text)
        for sentence in sentences:
            if keyword in sentence and len(sentence.strip()) >= 10:
                # 返回包含关键词的完整句子
                return sentence.strip()[:100]  # 最多100字
        return keyword  # fallback
    
    # 规则1: 付款但无违约金
    if "付款" in text and "违约金" not in text:
        quote = extract_quote("付款", text)
        findings.append(AuditFinding(
            summary="缺少违约金条款",
            detail="合同中包含付款义务，但未发现'违约金'相关表述，可能导致逾期付款时难以追责。",
            risk_level="warning",
            quote=quote
        ))
    
    # 规则2: 管辖权相关检查
    if "仲裁" in text and "法院" in text:
        quote = extract_quote("仲裁", text)
        findings.append(AuditFinding(
            summary="管辖权条款矛盾",
            detail="合同中同时出现'仲裁'和'法院'管辖，可能存在条款冲突。",
            risk_level="warning",
            quote=quote
        ))
    
    # 规则3: 单方解除权
    if "甲方有权单方" in text or "甲方可单方面" in text:
        keyword = "甲方有权单方" if "甲方有权单方" in text else "甲方可单方面"
        quote = extract_quote(keyword, text)
        findings.append(AuditFinding(
            summary="单方解除权不对等",
            detail="合同赋予甲方单方解除权，但未见乙方对等权利，存在权利不平衡风险。",
            risk_level="critical",
            quote=quote
        ))

    return {"rule_findings": findings}

async def llm_audit_node(state: ReviewState) -> Dict:
    """
    Uses LLM to find subtle risks with structured output.
    """
    logger.info("LLM Audit Node")
    llm = await LLMFactory.get_model(temperature=0.1, json_mode=True)
    
    prompt = f"""你是一名资深法务，请审查以下合同文本并找出风险点。

合同类型: {state['contract_type']}

审查重点：
1. 找出对甲方明显不利的隐藏条款
2. 检查是否有管辖权陷阱
3. 语言是否清晰，有无歧义
4. 付款条款是否合理
5. 违约责任是否对等

合同文本：
{state['text_content'][:6000]}

请以 JSON 格式输出审查结果。每个风险点必须包含：
- level: 风险等级 (critical/warning/info)
- summary: 风险标题（10字以内）
- detail: 详细说明（50-100字）
- quote: 合同原文中的相关句子（必须是合同中的原文，至少20个字，用于定位）

输出格式:
{{
  "findings": [
    {{
      "level": "warning",
      "summary": "违约金条款缺失",
      "detail": "合同中规定了付款义务，但未约定逾期付款的违约金或利息计算方式，可能导致维权困难。",
      "quote": "甲方应在收到货物后30日内支付全部货款"
    }}
  ]
}}

如果没有发现风险，返回: {{"findings": []}}
"""
    
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        content = response.content
        
        # 解析 JSON 响应
        import json
        import re
        
        # 尝试提取 JSON 内容（处理可能的 markdown 代码块包裹）
        json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            content = json_match.group(1)
        
        data = json.loads(content)
        findings = []
        
        for item in data.get("findings", []):
            level = item.get("level", "info").lower()
            if level not in ["critical", "warning", "info"]:
                level = "info"
            
            findings.append(AuditFinding(
                summary=item.get("summary", "AI 发现"),
                detail=item.get("detail", ""),
                risk_level=level,
                quote=item.get("quote"),  # 原文引用
                page=item.get("page")
            ))
        
        logger.info(f"LLM found {len(findings)} risks")
        return {"llm_findings": findings}
        
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse error: {e}, falling back to text parsing")
        # Fallback: 简单文本解析
        findings = []
        for line in content.split('\n'):
            if "Critical" in line or "Warning" in line or "critical" in line or "warning" in line:
                level = "critical" if "critical" in line.lower() else "warning"
                findings.append(AuditFinding(
                    summary="AI 智能发现",
                    detail=line.strip(),
                    risk_level=level
                ))
        return {"llm_findings": findings}
    except Exception as e:
        logger.error(f"LLM audit error: {e}")
        return {"llm_findings": []}

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
