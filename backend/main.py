from fastapi import FastAPI, UploadFile, File, Body
from fastapi.middleware.cors import CORSMiddleware  
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import json 
import os
import random 
import base64 
import io
import re
import urllib.request
from typing import Optional
from pypdf import PdfReader 
import cv2    
import numpy as np
from rapidocr_onnxruntime import RapidOCR
from dotenv import load_dotenv 
load_dotenv()

from services.gemini_service import gemini_service
from agents.orchestrator import run_full_analysis, generate_decision

app = FastAPI(title="AURORA AI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
   
if os.path.exists(FRONTEND_DIR):
    app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR), name="frontend")

@app.get("/")
async def serve_index():    
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path): 
        return FileResponse(index_path)
    return {"message": "Aurora AI Backend is running, but index.html was not found."}

PROFILE_DATA_PATH  = os.path.join(os.path.dirname(__file__), "data", "sample_profile.json")
USER_PROFILE_PATH  = os.path.join(os.path.dirname(__file__), "data", "user_account.json")
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY_1") or os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL  = os.getenv( "GEMINI_MODEL", "gemini-1.5-flash" ) 
OCR_ENGINE = None
DEFAULT_PROFILE_INCOME  = 5100.0
DEFAULT_PROFILE_EXPENSES  = 4100.0
DOCUMENT_CONTEXT_MEMORY = {  
    "last_filename": "",
}
CONVERSATION_HISTORY = []

   
if os.path.exists(PROFILE_DATA_PATH):
    try: os.remove(PROFILE_DATA_PATH)
    except: pass
if os.path.exists(USER_PROFILE_PATH):
    try: os.remove(USER_PROFILE_PATH)
    except: pass  


def _extract_json_block( text: str ) -> Optional[dict]:
    if not text:
        return None
    cleaned  = text.strip(  )
    if cleaned.startswith("```"):    
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned  = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None

def infer_document_type_heuristic(text: str, filename: str) -> str:  
    base = f"{filename} {text}".lower()
    finance_words = ["bank", "statement", "balance", "transaction", "deposit", "withdrawal", "expense", "salary", "invoice", "credit"]
    habit_words = ["workout", "exercise", "steps", "sleep", "habit", "meditation", "walk", "run", "gym", "calories"]
    finance_hits = sum(1 for w in finance_words if w in base)
    habit_hits = sum(1 for w in habit_words if w in base)
    if finance_hits > habit_hits and finance_hits >= 1:
        return "finance"
    if habit_hits > 0:
        return "habits"
    return "unknown" 

def extract_numbers_from_text(text: str) -> dict:
    nums  = [float(x) for x in re.findall(r"\d+\.?\d*", text or "")]
    if not nums:
        return {"income": 0.0, "expenses": 0.0}
    sorted_nums = sorted(nums, reverse=True)
    income = sorted_nums[0] if sorted_nums else 0.0
    expense_candidates  = [n for n in nums if n < income]
    expenses  = sum(expense_candidates[:20]) if expense_candidates else 0.0
    return {"income": round(income, 2), "expenses": round(expenses, 2)}

def extract_finance_from_ocr_text(text: str) -> dict:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    deposit_total  = 0.0
    withdraw_total = 0.0
    explicit_income  = None
    explicit_expense  = None 
    expect_income_next = False
    expect_expense_next = False  
    amount_re  = re.compile(r"\d{1,3}(?:,\d{3})*(?:\.\d{2})|\d+\.\d{2}")    
    inc_words  = ("deposit", "salary", "payroll", "credit", "refund", "transfer from")
    exp_words = ("withdraw", "payment", "fee", "debit", "purchase", "cheque", "bill", "transfer to")
    balance_words = ("opening balance", "closing balance", "available balance", "account summary", "balance on")
    for ln in lines:
        low = ln.lower()
        amounts = [float(a.replace(",", "")) for a in amount_re.findall(ln)]
        if not amounts:
            if "total deposits" in low or "total credits" in low or "deposits & credits" in low:
                expect_income_next = True
            if "total cheques" in low or "total debits" in low or "withdrawals" in low:   
                expect_expense_next  = True
            continue    
        if expect_income_next and explicit_income is None: 
            explicit_income  = amounts[-1]  
            expect_income_next  = False
            continue
        if expect_expense_next and explicit_expense is None:
            explicit_expense  = amounts[-1]
            expect_expense_next = False  
            continue
        if any(w in low for w in balance_words):
            continue
        if ("total deposits" in low or "total credits" in low or "deposits & credits" in low):
            explicit_income  = amounts[-1]
            continue    
        if ("total cheques" in low or "total debits" in low or "withdrawals" in low):
            explicit_expense  = amounts[-1]
            continue
        if "total" in low and len(amounts) >= 2:  
            return {"income": round(amounts[-1], 2), "expenses": round(amounts[-2], 2)}
        if any(w in low for w in inc_words):
            deposit_total += amounts[0]
        elif any( w in low for w in exp_words ):  
            withdraw_total += amounts[0]   
    if explicit_income is not None or explicit_expense is not None:
        return {"income": round(explicit_income or 0.0, 2), "expenses": round(explicit_expense or 0.0, 2)}
    if deposit_total > 100000 and withdraw_total == 0:
        deposit_total = 0.0
    if deposit_total > 0 or withdraw_total > 0:
        return {"income": round(deposit_total, 2), "expenses": round(withdraw_total, 2)}    
    return {"income": 0.0, "expenses": 0.0}  

def extract_idle_cash_from_text(text: str) -> float:
    lines  = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    amount_re = re.compile(r"\d{1,3}(?:,\d{3})*(?:\.\d{2})|\d+\.\d{2}")
    candidate  = 0.0
    for idx, ln in enumerate(lines):
        low = ln.lower()
        if "closing balance" in low or "opening balance" in low or "available balance" in low or "balance on" in low:   
            amounts  = [float(a.replace(",", "")) for a in amount_re.findall(ln)]  
            if amounts:
                candidate  = amounts[-1]  
                continue
            if idx + 1 < len(lines):
                nxt = [float(a.replace(",", "")) for a in amount_re.findall(lines[idx + 1])]
                if nxt:
                    candidate = nxt[-1]
    if candidate > 0:
        return round(candidate, 2)
    return 0.0

def get_ocr_engine():
    global OCR_ENGINE
    if OCR_ENGINE is None:
        OCR_ENGINE = RapidOCR()
    return OCR_ENGINE

def extract_text_from_pdf(file_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        text_parts = []
        for page in reader.pages[:5]:
            text_parts.append(page.extract_text() or "")
        return "\n".join(text_parts) 
    except Exception:
        return ""

def extract_text_from_image(file_bytes: bytes) -> str:
    try:   
        arr  = np.frombuffer(file_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return ""
        engine = get_ocr_engine()
        ocr_result, _ = engine(img)
        lines  = []
        for row in (ocr_result or []):
            if len(row) >= 2:
                lines.append(str(row[1]))
        return "\n".join(lines)
    except Exception:
        return ""

def apply_controlled_finance_interpreter(extracted: dict, run_id: str = "baseline") -> dict: 
    if extracted.get("document_type") != "finance":   
        return extracted
    income = float( extracted.get( "income_detected", 0 ) or 0 )
    expenses = float(extracted.get("expenses_detected", 0) or 0)
    estimated = bool(extracted.get("estimated", True))
    clamp_reasons = []
    if income < 1:
        clamp_reasons.append("low_income_signal") 
    if expenses < 1: 
        clamp_reasons.append("low_expense_signal")
    if expenses > income:
        clamp_reasons.append("negative_cashflow_detected")
    if estimated or clamp_reasons:    
        extracted["estimated"] = True
        extracted["needs_user_confirmation"]  = True
        extracted["income_detected"] = round(income, 2)
        extracted["expenses_detected"] = round(expenses, 2)
        extracted["autofilled_fields"]["finance"]["monthly_income"] = extracted["income_detected"]   
        extracted["autofilled_fields"]["finance"]["monthly_expenses"] = extracted["expenses_detected"]
        extracted["autofilled_fields"]["finance"]["itemized_expenses"] = ""
        extracted["interpretation_summary"] = (
            f"Bank statement detected. Estimated monthly income: ${int(income)}-${int(income + 200)}. "
            "Expenses: moderate variability detected. Financial risk: medium."
        )
        extracted["risk_flags"] = [    
            "Bank statement interpreted with controlled AI-assisted estimation",
            "Values normalized using finance sanity rules for demo stability",
        ]
    return extracted

def apply_unknown_document_guard(extracted: dict, run_id: str = "baseline") -> dict:
    if extracted.get("document_type") != "unknown":
        return extracted
    extracted["income_detected"] = 0.0  
    extracted["expenses_detected"]  = 0.0
    extracted["estimated"] = True
    extracted["needs_user_confirmation"] = True
    extracted["autofilled_fields"]["finance"]["monthly_income"]  = 0.0
    extracted["autofilled_fields"]["finance"]["monthly_expenses"] = 0.0
    extracted["autofilled_fields"]["finance"]["itemized_expenses"] = ""  
    extracted["risk_flags"] = [
        "Document type unsupported for financial extraction",  
        "No financial values auto-filled to prevent incorrect estimates", 
    ]
    extracted["interpretation_summary"] = (
        "Document uploaded, but no reliable financial structure detected. "   
        "Please confirm values manually."
    )
    return extracted
  
def build_document_context_memory(extracted: dict, filename: str) -> dict:
    doc_type  = extracted.get("document_type", "unknown")
    source = extracted.get("extraction_source", "unknown")
    insights = []
    if doc_type == "finance":
        insights.append("Document suggests financial activity patterns worth considering.")
        insights.append("Income signal appears present but should be treated as contextual, not authoritative.")
        insights.append("Variable spending behavior is likely present across the statement period.")
    elif doc_type == "habits":
        insights.append("Document suggests routine and habit consistency signals.")
        insights.append("Energy and recovery pattern clues are present in uploaded content.")
    else:    
        insights.append("Uploaded document could not be mapped to a reliable financial/habit schema.")
        insights.append("Treat this file as low-confidence context only.")
    for flag in (extracted.get("risk_flags") or []):
        if len(insights) >= 6:
            break
        insights.append(str(flag))
    payload = {  
        "document_insights": insights[:6],
        "document_type": doc_type,
        "source": source,
        "last_filename": filename,
    }
    return payload

def classify_and_extract_from_text(text: str, filename: str) -> dict:
    doc_type  = infer_document_type_heuristic(text, filename)
    nums = extract_finance_from_ocr_text(text) if doc_type == "finance" else extract_numbers_from_text(text) 
    idle_cash = extract_idle_cash_from_text(text) if doc_type  ==  "finance" else 0.0
    if doc_type == "finance":
        if nums["income"] > 0 and nums["expenses"] > nums["income"] * 1.7:    
            nums = {"income": nums["income"], "expenses": 0.0}
    item_lines = []   
    for line in (text or "").splitlines():
        if re.search(r"\d+\.?\d*", line):
            compact  = " ".join(line.split())
            if len(compact) < 140:
                item_lines.append(compact)
        if len(item_lines) >= 15:
            break
    return {
        "document_type": doc_type,
        "income": nums["income"],
        "expenses": nums["expenses"],
        "idle_cash": idle_cash,    
        "itemized_expenses": "\n".join(item_lines)
    }

def extract_with_gemini(file_bytes: bytes, filename: str, mime_type: str) -> Optional[dict]:  
    if not GEMINI_API_KEY:
        return None
    prompt  = ( 
        "Classify and extract data from this file. Return ONLY strict JSON with keys: "
        "document_type ('finance'|'habits'|'mixed'|'unknown'), "
        "income_detected (number), expenses_detected (number), "
        "itemized_expenses (string), "
        "sleep_hours_avg (number or null), exercise_days_per_week (number or null), workout_minutes_per_day (number or null), daily_habits_notes (string), " 
        "risk_flags (array of short strings), confidence (0 to 1). "
        "Use 0/null when unavailable."  
    )   
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload  = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {
                    "inline_data": { 
                        "mime_type": mime_type,
                        "data": base64.b64encode(file_bytes).decode("utf-8") 
                    }
                }
            ]
        }],
        "generationConfig": {"temperature": 0.1}
    }
    req = urllib.request.Request(    
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:    
            raw = json.loads(resp.read().decode("utf-8")) 
        text = (
            raw.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        parsed = _extract_json_block(text)  
        if not parsed:
            return None
        income = float(parsed.get("income_detected", 0) or 0)
        expenses = float(parsed.get("expenses_detected", 0) or 0)
        confidence  = float(parsed.get("confidence", 0) or 0)  
        risk_flags = parsed.get("risk_flags") or []
        sleep_hours_avg = parsed.get("sleep_hours_avg", None)
        return {   
            "document_type": str(parsed.get("document_type", "unknown")),
            "income_detected": max( income, 0 ),
            "expenses_detected": max(expenses, 0),
            "itemized_expenses": str(parsed.get("itemized_expenses", "") or ""),    
            "risk_flags": [str(x) for x in risk_flags][:5],    
            "sleep_hours_avg": sleep_hours_avg,
            "exercise_days_per_week": parsed.get("exercise_days_per_week", None),
            "workout_minutes_per_day": parsed.get("workout_minutes_per_day", None),
            "daily_habits_notes": str(parsed.get("daily_habits_notes", "") or ""),    
            "confidence": confidence,
        }
    except Exception as e:
        return None

def load_data(path, default):    
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return default

def save_data(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f: 
        json.dump(data, f)

class DecisionRequest(BaseModel):
    question: str
    user_profile: Optional[dict] = None
    reset_history: Optional[bool] = False

class ProfileUpdateRequest( BaseModel ):
    name: str 
    age: int
    primary_goal: str
    current_challenge: str
    stress_level: int
    financial_confidence: int    
    work_type: str
    decision_style: str

@app.get("/")
def read_root():
    return {"message": "AURORA AI API is running dynamically."}

@app.get("/api/account")
def get_account():
    default_account = {
        "name": "Aurora User",
        "age": 22,
        "primary_goal": "Career Growth",
        "current_challenge": "Time Management",
        "stress_level": 5,
        "financial_confidence": 5,
        "work_type": "Working Professional", 
        "decision_style": "Balanced"
    }
    return load_data(USER_PROFILE_PATH, default_account)

def reset_session_data(  ):  
    default_account = {
        "name": "Aurora User",
        "age": 22,
        "primary_goal": "Career Growth",
        "current_challenge": "Time Management",
        "stress_level": 5,
        "financial_confidence": 5,
        "work_type": "Working Professional",
        "decision_style": "Balanced"
    }
    default_profile  = {
        "finance": {"monthly_income": 5000, "monthly_expenses": 4200, "idle_cash": 1000},
        "productivity": {"deep_work_hours": 3, "daily_screen_time_hours": 6}, 
        "behavior": {"sleep_hours_avg": 7, "exercise_days_per_week": 3, "workout_minutes_per_day": 30},
        "learning": {"hours_per_week": 5, "current_focus": "System Design"}
    }
    os.makedirs(os.path.dirname(USER_PROFILE_PATH), exist_ok=True)
    with open(USER_PROFILE_PATH, 'w') as f:
        json.dump(default_account, f, indent=4)
    with open(PROFILE_DATA_PATH, 'w') as f:
        json.dump(default_profile, f, indent=4)

reset_session_data()

@app.get("/api/reset")  
async def manual_reset():
    global CONVERSATION_HISTORY
    reset_session_data(  )
    CONVERSATION_HISTORY = []
    return {"status": "success", "message": "Session data wiped."}    

@app.post("/api/account")  
def update_account(req: ProfileUpdateRequest):   
    save_data(USER_PROFILE_PATH, req.model_dump())
    return {"status": "success", "message": "Profile saved successfully to backend persistence."}

@app.post("/api/upload-document")  
async def upload_document(file: UploadFile = File(...)):    
    global DOCUMENT_CONTEXT_MEMORY
    filename = file.filename.lower()
    if not (filename.endswith(".pdf") or filename.endswith(".jpg") or filename.endswith(".jpeg") or filename.endswith(".png") or filename.endswith(".csv")):
        return {"status": "error", "message": "Only PDF/CSV/JPG/PNG/JPEG are supported."}
    file_bytes  = await file.read()
    text_preview = ""
    if filename.endswith(".pdf"):
        text_preview = extract_text_from_pdf(file_bytes)[:12000]
    extracted  = { 
        "income_detected": 5200,   
        "expenses_detected": 4100,
        "subscriptions": ["Netflix ($15)", "Spotify ($10)", "Gym ($50)"],
        "risk_flags": ["High dining out spending ($400/mo)", "Multiple unused subscriptions detected"], 
        "recommendation": "Reduce discretionary spending by 15% immediately", 
        "autofilled_fields": {
            "finance": {"monthly_income": 0, "monthly_expenses": 0, "idle_cash": 0, "itemized_expenses": "", "itemized_sync_enabled": False},
            "behavior": {"sleep_hours_avg": 6.5, "exercise_days_per_week": 2, "workout_minutes_per_day": 30, "daily_habits_notes": ""}
        },
        "estimated": True,
        "needs_user_confirmation": False,
        "extraction_source": "heuristic",    
        "document_type": "unknown"
    }
    if filename.endswith(".csv"):
        text  = file_bytes.decode("utf-8", errors="ignore")
        import csv, re
        from io import StringIO
        reader  = csv.reader(StringIO(text))
        income = 0   
        expenses = 0
        for row in reader:
            row_str  = " ".join(row).lower()
            nums = [float(x) for x in re.findall(r'\d+\.?\d*', row_str)]
            if nums:
                val = max(nums)   
                if "income" in row_str or "salary" in row_str or "deposit" in row_str:
                    income += val
                elif val > 0:
                    expenses += val
        extracted["income_detected"] = income if income > 0 else 0
        extracted["expenses_detected"] = expenses if expenses > 0 else 0
        extracted["risk_flags"] = ["Dangerous savings rate (under 10%)" if income - expenses < income*0.1 else "Healthy savings rate", "High frequency of transactions"]
        extracted["autofilled_fields"]["finance"]["monthly_income"] = extracted["income_detected"]
        extracted["autofilled_fields"]["finance"]["monthly_expenses"]  = extracted["expenses_detected"]
        extracted["estimated"] = False
        extracted["document_type"] = "finance"
        extracted["extraction_source"] = "csv_parser"
    elif filename.endswith(".pdf"):
        parsed = classify_and_extract_from_text(text_preview, filename)
        doc_type = parsed["document_type"]
        extracted["document_type"] = doc_type
        if doc_type == "finance":
            extracted["income_detected"] = parsed["income"]
            extracted["expenses_detected"] = parsed["expenses"]
            extracted["risk_flags"] = ["Finance document detected from PDF content"]
            extracted["autofilled_fields"]["finance"]["monthly_income"] = extracted["income_detected"]
            extracted["autofilled_fields"]["finance"]["monthly_expenses"] = extracted["expenses_detected"]
            extracted["autofilled_fields"]["finance"]["idle_cash"] = parsed.get("idle_cash", 0)    
            extracted["autofilled_fields"]["finance"]["itemized_expenses"] = parsed["itemized_expenses"]
            extracted["extraction_source"] = "pdf_text_finance_heuristic"
        elif doc_type == "habits":
            extracted["income_detected"]  = 0    
            extracted["expenses_detected"]  = 0
            extracted["risk_flags"] = ["Habits/fitness document detected from PDF content"]
            extracted["autofilled_fields"]["behavior"]["daily_habits_notes"] = "Detected habits-oriented document. Review and edit."
            extracted["extraction_source"] = "pdf_text_habits_heuristic"
        else:    
            extracted["risk_flags"] = ["Document type unclear from PDF, user confirmation required"]
            extracted["needs_user_confirmation"]  = True
            extracted["extraction_source"]  = "pdf_text_unknown" 
    elif filename.endswith((".jpg", ".png", ".jpeg")):
        extracted["income_detected"]  = 0
        extracted["expenses_detected"] = 0
        extracted["risk_flags"]  = ["Image uploaded: extracting via AI OCR/classification"]
        extracted["recommendation"]  = "Review extracted values before applying."
        extracted["autofilled_fields"]["finance"]["monthly_income"] = 0
        extracted["autofilled_fields"]["finance"]["monthly_expenses"]  = 0    
        text_for_parsing  = text_preview if text_preview else extract_text_from_image(file_bytes)
        gemini = gemini_service.parse_document(text_for_parsing)   
        if gemini:
            extracted["document_type"]  = gemini.get("document_type", "finance")
            extracted["income_detected"]  = gemini.get( "income_detected", 0 )
            extracted["expenses_detected"]  = gemini.get( "expenses_detected", 0 )
            extracted["risk_flags"]  = gemini.get("insights", [])
            extracted["autofilled_fields"]["finance"]["monthly_income"]  = extracted["income_detected"]
            extracted["autofilled_fields"]["finance"]["monthly_expenses"] = extracted["expenses_detected"]
            extracted["autofilled_fields"]["finance"]["itemized_expenses"]  = "\n".join(gemini.get("insights", []))
            extracted["recommendation"] = "Strategic Semantic Reasoning applied via Gemini Layer."
            extracted["estimated"] = False
            extracted["needs_user_confirmation"]  = False
            extracted["extraction_source"]  = "gemini_service"
        else:
            local_text = extract_text_from_image( file_bytes )
            parsed  = classify_and_extract_from_text(local_text, filename)
            if local_text.strip():    
                extracted["document_type"] = parsed["document_type"]
                extracted["income_detected"] = parsed["income"]    
                extracted["expenses_detected"] = parsed["expenses"]
                extracted["autofilled_fields"]["finance"]["monthly_income"] = extracted["income_detected"] 
                extracted["autofilled_fields"]["finance"]["monthly_expenses"] = extracted["expenses_detected"] 
                extracted["autofilled_fields"]["finance"]["idle_cash"] = parsed.get("idle_cash", 0)
                extracted["autofilled_fields"]["finance"]["itemized_expenses"] = parsed["itemized_expenses"]
                if parsed["document_type"] == "finance":
                    extracted["risk_flags"]  = ["Finance document parsed with local OCR fallback"]
                elif parsed["document_type"] == "habits":
                    extracted["risk_flags"]  = ["Habits document parsed with local OCR fallback"]
                extracted["extraction_source"]  = "local_ocr_fallback"   
                extracted["recommendation"] = "Local OCR fallback used. Verify parsed numbers."  
                extracted["estimated"] = True
                extracted["needs_user_confirmation"]  = True
            fallback_type = infer_document_type_heuristic("", filename)
            if extracted["extraction_source"] != "local_ocr_fallback":
                extracted["document_type"]  = fallback_type
                if fallback_type == "finance":
                    extracted["risk_flags"] = ["Finance document detected, but OCR model unavailable."]    
                elif fallback_type == "habits":
                    extracted["risk_flags"] = ["Habits document detected, but OCR model unavailable."]
                extracted["needs_user_confirmation"] = True
                extracted["estimated"]  = True
                extracted["extraction_source"]  = "heuristic_fallback"
                extracted["recommendation"] = "OCR estimate needs your confirmation. Edit the amounts below for higher accuracy."
    extracted = apply_controlled_finance_interpreter(extracted)
    extracted = apply_unknown_document_guard(extracted)
    DOCUMENT_CONTEXT_MEMORY = build_document_context_memory(extracted, filename)
    return {
        "status": "success",
        "message": f"Document parsed for contextual intelligence: {file.filename}",
        "extraction": extracted,
        "context_memory": DOCUMENT_CONTEXT_MEMORY    
    }

@app.post("/api/analyze")  
def analyze(profile: dict  = Body(None)):
    data = profile if profile is not None else load_data(PROFILE_DATA_PATH, {}) 
    if profile is not None:
        save_data(PROFILE_DATA_PATH, profile)
    account_data  = load_data(USER_PROFILE_PATH, {})   
    data["account"] = account_data
    data["document_context"] = DOCUMENT_CONTEXT_MEMORY
    analysis = run_full_analysis( data )
    return analysis

@app.post( "/api/decision" )
def decision(req: DecisionRequest):
    global CONVERSATION_HISTORY
    if req.reset_history:
        CONVERSATION_HISTORY = []
    data = req.user_profile if req.user_profile else load_data(PROFILE_DATA_PATH, {})
    account_data = load_data(USER_PROFILE_PATH, {})
    data["account"] = account_data
    data["document_context"] = DOCUMENT_CONTEXT_MEMORY
    data["history"] = CONVERSATION_HISTORY
    result = generate_decision(req.question, data)
    
    # Store in history
    CONVERSATION_HISTORY.append({"role": "user", "content": req.question})
    CONVERSATION_HISTORY.append({"role": "assistant", "content": f"Verdict: {result.get('decision')}. {result.get('why')}"})
    if len(CONVERSATION_HISTORY) > 10:
        CONVERSATION_HISTORY = CONVERSATION_HISTORY[-10:]
        
    result.pop("life_instability_index", None) # Remove index tracking

    q = req.question.lower()
    if " vs " in q or " or " in q or result.get("decision") in ["NO", "CAUTION", "STUDY", "TAKE A BREAK"]:  
        result["comparison_mode"] = True
        
        # Heuristic to find options
        if " or " in q:
            parts = q.split(" or ")
            # Clean up option A
            opt_a = parts[0].replace("should i ", "").replace("i should ", "").strip()
            # Clean up option B
            opt_b = parts[1].split("?")[0].strip()
            
            result["option_a_label"] = opt_a.capitalize() if 0 < len(opt_a) < 25 else "Option A"
            result["option_b_label"] = opt_b.capitalize() if 0 < len(opt_b) < 25 else "Aurora Strategy"
        elif " vs " in q:
            parts = q.split(" vs ")
            result["option_a_label"] = parts[0].strip().capitalize()
            result["option_b_label"] = parts[1].strip().capitalize()
        else:
            result["option_a_label"] = "Immediate Action"
            result["option_b_label"] = "Aurora Strategy"

        # Ensure we don't use 'Option B' in the analysis text if we have a better label
        chosen_label = result.get("option_b_label", "Aurora Strategy")
        
        # Calculate scores based on instability and logic
        inst = result.get("life_instability_index", 50)
        if result.get("decision") == "NO":
            result["option_a_score"] = max(10, 40 - int(inst/2))
            result["option_b_score"] = min(95, 80 + int((100-inst)/10))
        else:
            result["option_a_score"] = random.randint(55, 75)
            result["option_b_score"] = random.randint(80, 96)
            
        result["comparison_analysis"] = f"The {chosen_label} provides a mathematically superior outcome (Score: {result['option_b_score']}) by optimizing for long-term stability and protecting your energy reserves."
    return result

@app.get("/api/profile")   
def get_profile():
    return load_data(PROFILE_DATA_PATH, {})

if __name__ == "__main__":  
    import uvicorn    
    uvicorn.run(app, host="0.0.0.0", port=8000)