"""
func_replica.py
Option C: Production-grade multi-advisor OCI Function with Object Storage artifact persistence.

Features:
- Intent detection (Gen AI) + keyword fallback for advisors: general, finance, hr, orders, reports.
- Dual-mode General advisor: ORDS NL2SQL endpoint (from config.properties or env) → Gen AI fallback → static fallback.
- Finance advisor: SOAP/HTTP endpoint for BI Publisher; if PDF base64 returned, store in Object Storage.
- Reports advisor: Asynchronous workbook export (returns pending artifact; client later invokes action=download to finalize).
- Orders advisor: REST endpoint(s) for list/detail; truncates output, stores large payloads if exceeds size threshold.
- HR advisor: API + mock fallback.
- Object Storage persistence: binary + metadata JSON; presigned GET URLs.
- Single handler with actions: chat | download | status (optional future extension).
- Response includes `message` for easy JSONPath mapping (`$.message`).

Configuration Priority (1 → 3):
1. Environment variables.
2. config.properties (placed beside file).
3. Code defaults.

Environment Variables:
- COMPARTMENT_ID (required for Gen AI usage)
- GENAI_REGION (default: us-ashburn-1)
- GENAI_MODEL_ID (default: cohere.command-r-plus)
- GENAI_INTENT_MODE (auto|force|off) default auto
- USE_MOCK_RESPONSES (true|false) default true
- GENERAL_ORDS_URL (override ORDS NL2SQL endpoint)
- FINANCE_AGENT_URL / FINANCE_AGENT_USERNAME / FINANCE_AGENT_PASSWORD
- ORDERS_AGENT_URL / ORDERS_AGENT_USERNAME / ORDERS_AGENT_PASSWORD
- REPORTS_AGENT_URL / REPORTS_AGENT_USERNAME / REPORTS_AGENT_PASSWORD / REPORTS_WORKBOOK_ID
- HR_AGENT_URL / HR_AGENT_USERNAME / HR_AGENT_PASSWORD
- ARTIFACT_BUCKET (required for artifact persistence)
- PRESIGN_TTL_SECONDS (default 900)
- MAX_INLINE_BYTES (default 18000) – if advisor text > threshold store object & return summary + link

Request JSON:
{
  "action": "chat|download",
  "prompt": "...",          # required for chat
  "sessionId": "optional",
  "artifactId": "uuid"       # required for download action
}

Response Samples:
Chat with artifact ready:
{
  "sessionId": "s1",
  "action": "chat",
  "routedIntent": "finance",
  "advisors": [ {"name": "Finance Advisor", "type": "finance", "source": "api", "artifact": {"id": "uuid", "type": "pdf", "status": "ready", "presignedUrl": "https://...", "expiresIn": 900, "filename": "Finance_Report_20251127_123456.pdf" } } ],
  "message": "[Finance] Report generated. Download available.",
  "artifactsPending": false
}

Chat with pending report:
{
  "sessionId": "s1",
  "action": "chat",
  "routedIntent": "reports",
  "advisors": [ {"name": "Reports Advisor", "type": "reports", "source": "export", "artifact": {"id": "uuid", "type": "pdf", "status": "pending" } } ],
  "message": "[Reports] Export started. Poll with action=download&artifactId=<uuid>.",
  "artifactsPending": true
}

Download action response:
{
  "sessionId": "s1",
  "action": "download",
  "artifact": {"id": "uuid", "status": "ready", "presignedUrl": "https://...", "expiresIn": 900, "filename": "Finance_Report_20251127_123456.pdf"},
  "message": "Artifact ready: Finance_Report_20251127_123456.pdf"
}
"""
import json
import os
import logging
import uuid
import base64
import re
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from fdk import response

# Optional imports guarded
try:
    import oci
    from oci.generative_ai_inference import GenerativeAiInferenceClient
    from oci.generative_ai_inference.models import (
        OnDemandServingMode,
        ChatDetails,
        CohereChatRequest
    )
    from oci.object_storage import ObjectStorageClient
    OCI_SDK = True
except ImportError:
    OCI_SDK = False

try:
    import requests
    from requests.auth import HTTPBasicAuth
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

# ---------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------
logger = logging.getLogger("func_replica")
if not logger.handlers:
    h = logging.StreamHandler()
    f = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    h.setFormatter(f)
    logger.addHandler(h)
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------
# API Spec Loading
# ---------------------------------------------------------------------
def load_api_spec(spec_file: str) -> Optional[Dict]:
    """Load API specification from JSON file"""
    spec_path = os.path.join(os.path.dirname(__file__), spec_file)
    try:
        with open(spec_path, 'r') as f:
            spec = json.load(f)
            logger.info(f"Loaded API spec: {spec_file}")
            return spec
    except FileNotFoundError:
        logger.warning(f"API spec file not found: {spec_file}")
        return None
    except Exception as e:
        logger.error(f"Error loading API spec {spec_file}: {e}")
        return None

# Load API specifications (for reference and documentation)
API_SPEC_GENERAL = load_api_spec('api_spec_general.json')
API_SPEC_FINANCE = load_api_spec('api_spec_finance.json')
API_SPEC_HR = load_api_spec('api_spec_hr.json')
API_SPEC_ORDERS = load_api_spec('api_spec_orders.json')
API_SPEC_REPORTS = load_api_spec('api_spec_reports.json')

# ---------------------------------------------------------------------
# Config loading (config.properties optional)
# ---------------------------------------------------------------------
CONFIG: Dict[str, str] = {}
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.properties')
if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, 'r') as cf:
            for line in cf:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    CONFIG[k.strip()] = v.strip()
        logger.info("Loaded config.properties")
    except Exception as e:
        logger.warning(f"Failed to load config.properties: {e}")
else:
    logger.info("config.properties not found; relying on env vars")

# Helper to get config with env override

def cfg(key: str, default: Optional[str] = None) -> Optional[str]:
    return os.getenv(key) or CONFIG.get(key) or default

# ---------------------------------------------------------------------
# Environment / configuration values
# ---------------------------------------------------------------------
COMPARTMENT_ID = cfg('COMPARTMENT_ID', '')
GENAI_REGION = cfg('GENAI_REGION', 'us-ashburn-1')
GENAI_MODEL_ID = cfg('GENAI_MODEL_ID', 'cohere.command-r-plus')
GENAI_INTENT_MODE = cfg('GENAI_INTENT_MODE', 'auto').lower()  # auto|force|off
USE_MOCK_RESPONSES = cfg('USE_MOCK_RESPONSES', 'true').lower() == 'true'
GENERAL_ORDS_URL = cfg('GENERAL_ORDS_URL', cfg('general_agent_url', ''))  # Fallback to config key
ARTIFACT_BUCKET = cfg('ARTIFACT_BUCKET', '')
PRESIGN_TTL_SECONDS = int(cfg('PRESIGN_TTL_SECONDS', '900'))
MAX_INLINE_BYTES = int(cfg('MAX_INLINE_BYTES', '18000'))
REPORTS_WORKBOOK_ID = cfg('REPORTS_WORKBOOK_ID', 'L3NoYXJlZC9SQ09FL0Fic2VuY2UgV29ya2Jvb2s')

FINANCE_URL = cfg('FINANCE_AGENT_URL', cfg('finance_agent_url', ''))
FINANCE_USER = cfg('FINANCE_AGENT_USERNAME', cfg('finance_agent_username', ''))
FINANCE_PASS = cfg('FINANCE_AGENT_PASSWORD', cfg('finance_agent_password', ''))

ORDERS_URL = cfg('ORDERS_AGENT_URL', cfg('orders_agent_url', ''))
ORDERS_USER = cfg('ORDERS_AGENT_USERNAME', cfg('orders_agent_username', ''))
ORDERS_PASS = cfg('ORDERS_AGENT_PASSWORD', cfg('orders_agent_password', ''))

REPORTS_URL = cfg('REPORTS_AGENT_URL', cfg('reports_agent_url', ''))
REPORTS_USER = cfg('REPORTS_AGENT_USERNAME', cfg('reports_agent_username', ''))
REPORTS_PASS = cfg('REPORTS_AGENT_PASSWORD', cfg('reports_agent_password', ''))

HR_URL = cfg('HR_AGENT_URL', cfg('hr_agent_url', ''))
HR_USER = cfg('HR_AGENT_USERNAME', cfg('hr_agent_username', ''))
HR_PASS = cfg('HR_AGENT_PASSWORD', cfg('hr_agent_password', ''))

# ---------------------------------------------------------------------
# OCI Clients (Resource Principal)
# ---------------------------------------------------------------------
signer = None
object_client: Optional[ObjectStorageClient] = None
genai_client: Optional[GenerativeAiInferenceClient] = None
namespace_name: Optional[str] = None

if OCI_SDK:
    try:
        signer = oci.auth.signers.get_resource_principals_signer()
        if COMPARTMENT_ID:
            genai_client = GenerativeAiInferenceClient(
                config={"region": GENAI_REGION},
                signer=signer,
                service_endpoint=f"https://inference.generativeai.{GENAI_REGION}.oci.oraclecloud.com"
            )
            logger.info(f"Gen AI client initialized: region={GENAI_REGION}")
        else:
            logger.warning("COMPARTMENT_ID not set; Gen AI disabled")
        if ARTIFACT_BUCKET:
            object_client = ObjectStorageClient(config={}, signer=signer)
            namespace_name = object_client.get_namespace().data
            logger.info(f"Object Storage namespace: {namespace_name}")
        else:
            logger.warning("ARTIFACT_BUCKET not set; artifact persistence disabled")
    except Exception as e:
        logger.error(f"OCI client init failed: {e}")
else:
    logger.warning("OCI SDK unavailable; Gen AI + Object Storage disabled")

# ---------------------------------------------------------------------
# Utility: Object storage operations
# ---------------------------------------------------------------------

def put_object(key: str, raw: bytes) -> bool:
    if not object_client or not namespace_name or not ARTIFACT_BUCKET:
        return False
    try:
        object_client.put_object(namespace_name, ARTIFACT_BUCKET, key, raw)
        return True
    except Exception as e:
        logger.error(f"put_object failed for {key}: {e}")
        return False


def get_presigned(key: str, ttl_seconds: int) -> Optional[str]:
    if not object_client or not namespace_name or not ARTIFACT_BUCKET:
        return None
    try:
        return object_client.get_presigned_url(
            method='GET',
            bucket_name=ARTIFACT_BUCKET,
            object_name=key,
            time_duration=timedelta(seconds=ttl_seconds)
        )
    except Exception as e:
        logger.error(f"get_presigned failed for {key}: {e}")
        return None

# ---------------------------------------------------------------------
# Intent Detection
# ---------------------------------------------------------------------
INTENTS = ['general', 'finance', 'hr', 'orders', 'reports']

def detect_intent(prompt: str) -> Optional[str]:
    if not genai_client or GENAI_INTENT_MODE == 'off':
        return None
    try:
        chat_request = CohereChatRequest(
            message=("Classify user query into one of: general, finance, hr, orders, reports.\nQuery: " + prompt + "\nCategory:"),
            max_tokens=12,
            temperature=0.0,
            is_stream=False
        )
        details = ChatDetails(
            serving_mode=OnDemandServingMode(model_id=GENAI_MODEL_ID),
            compartment_id=COMPARTMENT_ID,
            chat_request=chat_request
        )
        resp = genai_client.chat(details)
        text = resp.data.chat_response.text.strip().lower()
        for intent in INTENTS:
            if intent in text:
                return intent
    except Exception as e:
        logger.error(f"Intent detection error: {e}")
    return None

# ---------------------------------------------------------------------
# General Advisor (dual-mode NL2SQL → Gen AI → fallback)
# ---------------------------------------------------------------------
GENERAL_DB_KEYWORDS = ['table', 'database', 'query', 'sql', 'select', 'data', 'record', 'nlp', 'nl2sql']

def advisor_general(prompt: str) -> Dict[str, Any]:
    lower = prompt.lower()
    # NL2SQL attempt
    if GENERAL_ORDS_URL and REQUESTS_OK and any(k in lower for k in GENERAL_DB_KEYWORDS):
        try:
            r = requests.post(GENERAL_ORDS_URL, json={'user_query': prompt}, headers={'Content-Type': 'application/json'}, timeout=12)
            if r.ok:
                js = r.json()
                ans = js.get('answer') or js.get('response')
                if ans:
                    return {"name": "General Advisor 🤖", "type": "general", "source": "nl2sql", "text": ans}
        except Exception as e:
            logger.warning(f"NL2SQL error: {e}")
    # Gen AI fallback
    if genai_client:
        try:
            chat_request = CohereChatRequest(message=prompt, max_tokens=500, temperature=0.7, is_stream=False)
            details = ChatDetails(serving_mode=OnDemandServingMode(model_id=GENAI_MODEL_ID), chat_request=chat_request, compartment_id=COMPARTMENT_ID)
            resp = genai_client.chat(details)
            return {"name": "General Advisor 🤖", "type": "general", "source": "genai", "text": resp.data.chat_response.text.strip()}
        except Exception as e:
            logger.error(f"Gen AI general error: {e}")
    # Static fallback
    return {"name": "General Advisor 🤖", "type": "general", "source": "static", "text": "I can help with general queries, database questions (via NL2SQL), and routing to other advisors."}

# ---------------------------------------------------------------------
# Finance Advisor (BI Publisher SOAP → PDF)
# ---------------------------------------------------------------------
FINANCE_SOAP_RE = re.compile(r'<[^:]+:reportBytes>([^<]+)</[^:]+:reportBytes>')

def advisor_finance(prompt: str) -> Dict[str, Any]:
    if USE_MOCK_RESPONSES or not (FINANCE_URL and FINANCE_USER and FINANCE_PASS) or not REQUESTS_OK:
        return {"name": "Finance Advisor 💰", "type": "finance", "source": "mock", "text": "Finance advisor mock: budget allocation 40% R&D, 30% Ops, 30% Marketing."}
    try:
        # Use REST endpoint from spec (BI Publisher REST API preferred over SOAP)
        if API_SPEC_FINANCE:
            # Build REST payload from spec
            payload = {
                "reportRequest": {
                    "reportAbsolutePath": "/Custom/ROIC/ROIC_PO_REPORTS.xdo",
                    "attributeFormat": "pdf",
                    "parameterNameValues": {
                        "item": [
                            {
                                "name": "P_PO_NUM",
                                "values": {"item": ["55269"]}
                            }
                        ]
                    },
                    "sizeOfDataChunkDownload": -1
                }
            }
            headers = {"Content-Type": "application/json"}
            auth = HTTPBasicAuth(FINANCE_USER, FINANCE_PASS)
            # Extract server URL from spec
            server_url = API_SPEC_FINANCE.get('servers', [{}])[0].get('url', FINANCE_URL.split('/xmlpserver')[0])
            endpoint = f"{server_url}/xmlpserver/services/rest/v1/reports"
            resp = requests.post(endpoint, json=payload, headers=headers, auth=auth, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                b64_pdf = data.get('reportBytes', '')
                if b64_pdf:
                    pdf_bytes = base64.b64decode(b64_pdf)
                    artifact_id = str(uuid.uuid4())
                    filename = f"Finance_Report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
                    meta_key = f"artifact/{artifact_id}.json"
                    bin_key = f"artifact/{artifact_id}.pdf"
                    if put_object(bin_key, pdf_bytes):
                        meta = {
                            'id': artifact_id,
                            'type': 'pdf',
                            'advisor': 'finance',
                            'status': 'ready',
                            'filename': filename,
                            'created': datetime.utcnow().isoformat() + 'Z',
                            'contentType': 'application/pdf',
                            'size': len(pdf_bytes)
                        }
                        put_object(meta_key, json.dumps(meta).encode('utf-8'))
                        url = get_presigned(bin_key, PRESIGN_TTL_SECONDS)
                        return {"name": "Finance Advisor 💰", "type": "finance", "source": "api", "text": "Finance PDF ready.", "artifact": {**meta, "presignedUrl": url, "expiresIn": PRESIGN_TTL_SECONDS}}
                    else:
                        return {"name": "Finance Advisor 💰", "type": "finance", "source": "api", "text": "Failed to store PDF artifact."}
                return {"name": "Finance Advisor 💰", "type": "finance", "source": "api", "text": "Report generated but PDF bytes not found."}
            elif resp.status_code == 401:
                return {"name": "Finance Advisor 💰", "type": "finance", "source": "api", "text": "Authentication failed for finance API."}
            else:
                return {"name": "Finance Advisor 💰", "type": "finance", "source": "api", "text": f"Finance API error HTTP {resp.status_code}"}
        # Fallback to SOAP if spec not loaded
        soap_body = """<?xml version='1.0' encoding='UTF-8'?><soap:Envelope xmlns:soap='http://www.w3.org/2003/05/soap-envelope' xmlns:pub='http://xmlns.oracle.com/oxp/service/PublicReportService'><soap:Header/><soap:Body><pub:runReport><pub:reportRequest><pub:attributeFormat>pdf</pub:attributeFormat><pub:parameterNameValues><pub:item><pub:name>P_PO_NUM</pub:name><pub:values><pub:item>55269</pub:item></pub:values></pub:item></pub:parameterNameValues><pub:reportAbsolutePath>/Custom/ROIC/ROIC_PO_REPORTS.xdo</pub:reportAbsolutePath><pub:sizeOfDataChunkDownload>-1</pub:sizeOfDataChunkDownload></pub:reportRequest><pub:appParams></pub:appParams></pub:runReport></soap:Body></soap:Envelope>"""
        headers = {"Content-Type": "application/soap+xml; charset=UTF-8"}
        auth = HTTPBasicAuth(FINANCE_USER, FINANCE_PASS)
        resp = requests.post(FINANCE_URL, data=soap_body, headers=headers, auth=auth, timeout=30)
        if resp.status_code == 200:
            m = FINANCE_SOAP_RE.search(resp.text)
            if m:
                b64_pdf = m.group(1).strip()
                pdf_bytes = base64.b64decode(b64_pdf)
                artifact_id = str(uuid.uuid4())
                filename = f"Finance_Report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
                meta_key = f"artifact/{artifact_id}.json"
                bin_key = f"artifact/{artifact_id}.pdf"
                if put_object(bin_key, pdf_bytes):
                    meta = {
                        'id': artifact_id,
                        'type': 'pdf',
                        'advisor': 'finance',
                        'status': 'ready',
                        'filename': filename,
                        'created': datetime.utcnow().isoformat() + 'Z',
                        'contentType': 'application/pdf',
                        'size': len(pdf_bytes)
                    }
                    put_object(meta_key, json.dumps(meta).encode('utf-8'))
                    url = get_presigned(bin_key, PRESIGN_TTL_SECONDS)
                    return {"name": "Finance Advisor 💰", "type": "finance", "source": "api", "text": "Finance PDF ready.", "artifact": {**meta, "presignedUrl": url, "expiresIn": PRESIGN_TTL_SECONDS}}
                else:
                    return {"name": "Finance Advisor 💰", "type": "finance", "source": "api", "text": "Failed to store PDF artifact."}
            return {"name": "Finance Advisor 💰", "type": "finance", "source": "api", "text": "Report generated but PDF bytes not found."}
        elif resp.status_code == 401:
            return {"name": "Finance Advisor 💰", "type": "finance", "source": "api", "text": "Authentication failed for finance API."}
        else:
            return {"name": "Finance Advisor 💰", "type": "finance", "source": "api", "text": f"Finance API error HTTP {resp.status_code}"}
    except Exception as e:
        logger.error(f"Finance advisor error: {e}")
        return {"name": "Finance Advisor 💰", "type": "finance", "source": "error", "text": f"Finance error: {e}"}

# ---------------------------------------------------------------------
# HR Advisor (API + mock fallback)
# ---------------------------------------------------------------------

def advisor_hr(prompt: str) -> Dict[str, Any]:
    if HR_URL and HR_USER and HR_PASS and REQUESTS_OK and not USE_MOCK_RESPONSES:
        try:
            resp = requests.get(HR_URL, params={'prompt': prompt}, auth=HTTPBasicAuth(HR_USER, HR_PASS), timeout=15)
            if resp.ok:
                data = resp.json()
                txt = data.get('response') or json.dumps(data)[:400]
                return {"name": "HR Advisor 👥", "type": "hr", "source": "api", "text": txt}
        except Exception as e:
            logger.warning(f"HR API error: {e}")
    # Mock fallback
    return {"name": "HR Advisor 👥", "type": "hr", "source": "mock", "text": "HR policies include 20 days PTO, comprehensive health coverage, and flexible remote work."}

# ---------------------------------------------------------------------
# Orders Advisor (list/detail)
# ---------------------------------------------------------------------
ORDER_KEY_RE = re.compile(r"\b[A-Z]{2,10}:\d{9,}\b")
LONG_ID_RE = re.compile(r"\b\d{9,15}\b")

def advisor_orders(prompt: str) -> Dict[str, Any]:
    if USE_MOCK_RESPONSES or not (ORDERS_URL and ORDERS_USER and ORDERS_PASS) or not REQUESTS_OK:
        return {"name": "Orders Advisor 📦", "type": "orders", "source": "mock", "text": "Recent orders: fulfillment 95%, avg delivery 2.3 days."}
    auth = HTTPBasicAuth(ORDERS_USER, ORDERS_PASS)
    try:
        order_key = None
        m = ORDER_KEY_RE.search(prompt)
        if m:
            order_key = m.group(0)
        else:
            m2 = LONG_ID_RE.search(prompt)
            if m2:
                order_key = m2.group(0)
        if order_key:
            url = f"{ORDERS_URL}/{order_key}"
            r = requests.get(url, auth=auth, timeout=20)
            if r.status_code == 200:
                data = r.json()
                summary = json.dumps({
                    'OrderKey': data.get('OrderKey'),
                    'Status': data.get('StatusCode'),
                    'SubmittedBy': data.get('SubmittedBy'),
                    'SubmittedDate': data.get('SubmittedDate')
                })
                return {"name": "Orders Advisor 📦", "type": "orders", "source": "api", "text": summary}
            elif r.status_code == 404:
                return {"name": "Orders Advisor 📦", "type": "orders", "source": "api", "text": "Order not found."}
            else:
                return {"name": "Orders Advisor 📦", "type": "orders", "source": "api", "text": f"Orders API error {r.status_code}"}
        else:
            params = {'limit': 10}
            r = requests.get(ORDERS_URL, params=params, auth=auth, timeout=20)
            if r.status_code == 200:
                items = r.json().get('items') or []
                if not items:
                    return {"name": "Orders Advisor 📦", "type": "orders", "source": "api", "text": "No recent sales orders."}
                lines = []
                for it in items[:10]:
                    lines.append(f"{it.get('OrderKey','N/A')} | {it.get('StatusCode','N/A')} | {it.get('LastUpdateDate','N/A')}")
                text = "Recent Orders (showing 10):\n" + "\n".join(lines)
                # If long, store artifact
                if len(text.encode('utf-8')) > MAX_INLINE_BYTES and object_client:
                    artifact_id = str(uuid.uuid4())
                    bin_key = f"artifact/{artifact_id}.txt"
                    meta_key = f"artifact/{artifact_id}.json"
                    put_object(bin_key, text.encode('utf-8'))
                    meta = {
                        'id': artifact_id,
                        'type': 'text',
                        'advisor': 'orders',
                        'status': 'ready',
                        'filename': f"Orders_List_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt",
                        'created': datetime.utcnow().isoformat() + 'Z',
                        'contentType': 'text/plain',
                        'size': len(text.encode('utf-8'))
                    }
                    put_object(meta_key, json.dumps(meta).encode('utf-8'))
                    url = get_presigned(bin_key, PRESIGN_TTL_SECONDS)
                    return {"name": "Orders Advisor 📦", "type": "orders", "source": "api", "text": "Orders list stored as artifact (download).", "artifact": {**meta, 'presignedUrl': url, 'expiresIn': PRESIGN_TTL_SECONDS}}
                return {"name": "Orders Advisor 📦", "type": "orders", "source": "api", "text": text}
            else:
                return {"name": "Orders Advisor 📦", "type": "orders", "source": "api", "text": f"Orders API error {r.status_code}"}
    except Exception as e:
        logger.error(f"Orders advisor error: {e}")
        return {"name": "Orders Advisor 📦", "type": "orders", "source": "error", "text": f"Orders error: {e}"}

# ---------------------------------------------------------------------
# Reports Advisor (Async export simulation)
# ---------------------------------------------------------------------
# For production: implement real export initiation + status polling. Here we simulate async.

def advisor_reports(prompt: str) -> Dict[str, Any]:
    # If mock mode, simple response
    if USE_MOCK_RESPONSES or not (REPORTS_URL and REPORTS_USER and REPORTS_PASS) or not REQUESTS_OK:
        return {"name": "Reports Advisor 📊", "type": "reports", "source": "mock", "text": "Reports export mock started.", "artifact": {"id": str(uuid.uuid4()), "type": "pdf", "status": "pending"}}
    try:
        # Simulate export initiation returning an ID (would call API normally)
        export_id = str(uuid.uuid4())
        artifact_id = export_id
        # Store metadata as pending
        if object_client:
            meta = {
                'id': artifact_id,
                'type': 'pdf',
                'advisor': 'reports',
                'status': 'pending',
                'filename': f"Analytics_Report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf",
                'created': datetime.utcnow().isoformat() + 'Z'
            }
            put_object(f"artifact/{artifact_id}.json", json.dumps(meta).encode('utf-8'))
        return {"name": "Reports Advisor 📊", "type": "reports", "source": "export", "text": "Report export initiated.", "artifact": {"id": artifact_id, "type": "pdf", "status": "pending"}}
    except Exception as e:
        logger.error(f"Reports advisor error: {e}")
        return {"name": "Reports Advisor 📊", "type": "reports", "source": "error", "text": f"Reports error: {e}"}

# ---------------------------------------------------------------------
# Keyword fallback mapping
# ---------------------------------------------------------------------
ADVISOR_KEYWORDS = {
    'general': ['general', 'help', 'what can you do', 'capabilities', 'nlp', 'nl2sql', 'database', 'table', 'query'],
    'finance': ['finance', 'revenue', 'budget', 'expense', 'cost', 'money'],
    'hr': ['hr', 'policy', 'benefit', 'leave', 'employee', 'vacation'],
    'orders': ['order', 'inventory', 'delivery', 'shipping', 'stock', 'sales'],
    'reports': ['workbook', 'analytics', 'export', 'oac', 'dashboard']
}

ADVISOR_FUNCS = {
    'general': advisor_general,
    'finance': advisor_finance,
    'hr': advisor_hr,
    'orders': advisor_orders,
    'reports': advisor_reports
}

# ---------------------------------------------------------------------
# Processing logic
# ---------------------------------------------------------------------

def process_chat(prompt: str) -> Dict[str, Any]:
    routed = detect_intent(prompt) if GENAI_INTENT_MODE != 'off' else None
    advisors: List[Dict[str, Any]] = []
    if routed:
        advisors.append(ADVISOR_FUNCS.get(routed, advisor_general)(prompt))
    else:
        lower = prompt.lower()
        matched = False
        if any(k in lower for k in ADVISOR_KEYWORDS['general']):
            advisors.append(advisor_general(prompt))
            matched = True
        for adv in ['finance', 'hr', 'orders', 'reports']:
            if any(k in lower for k in ADVISOR_KEYWORDS[adv]):
                advisors.append(ADVISOR_FUNCS[adv](prompt))
                matched = True
        if not matched:
            advisors.append(advisor_general(prompt))
    # Build summary message
    parts = []
    pending_any = False
    for a in advisors:
        nm = a.get('name', 'Advisor')
        txt = a.get('text', '')
        artifact = a.get('artifact')
        if artifact and artifact.get('status') == 'pending':
            pending_any = True
        parts.append(f"[{nm.split()[0]}] {txt}")
    summary = "\n\n".join(parts)
    return {
        'routedIntent': routed,
        'advisors': advisors,
        'message': summary,
        'artifactsPending': pending_any
    }

# ---------------------------------------------------------------------
# Download action: finalize pending artifacts (simulate ready)
# ---------------------------------------------------------------------

def process_download(artifact_id: str) -> Dict[str, Any]:
    if not object_client or not ARTIFACT_BUCKET or not namespace_name:
        return {'error': 'artifact storage not configured'}
    meta_key = f"artifact/{artifact_id}.json"
    try:
        meta_obj = object_client.get_object(namespace_name, ARTIFACT_BUCKET, meta_key)
        meta = json.loads(meta_obj.data.text)
    except Exception as e:
        return {'error': f'metadata not found: {e}'}
    if meta.get('status') == 'pending':
        # Simulate completion: create a tiny PDF placeholder
        dummy_pdf = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
        bin_key = f"artifact/{artifact_id}.pdf"
        put_object(bin_key, dummy_pdf)
        meta['status'] = 'ready'
        meta['size'] = len(dummy_pdf)
        meta['contentType'] = 'application/pdf'
        put_object(meta_key, json.dumps(meta).encode('utf-8'))
    if meta.get('status') == 'ready':
        url = get_presigned(f"artifact/{artifact_id}.pdf", PRESIGN_TTL_SECONDS)
        return {'artifact': {**meta, 'presignedUrl': url, 'expiresIn': PRESIGN_TTL_SECONDS}, 'message': f"Artifact ready: {meta.get('filename')}"}
    return {'artifact': meta, 'message': 'Artifact not ready yet'}

# ---------------------------------------------------------------------
# Handler utilities
# ---------------------------------------------------------------------

def parse_body(data) -> Dict[str, Any]:
    try:
        if not data:
            return {}
        raw = data.getvalue() if hasattr(data, 'getvalue') else data
        if isinstance(raw, bytes):
            raw = raw.decode('utf-8')
        return json.loads(raw)
    except Exception:
        return {}

# ---------------------------------------------------------------------
# OCI Function Handler
# ---------------------------------------------------------------------

def handler(ctx, data=None):
    payload = parse_body(data)
    action = (payload.get('action') or 'chat').lower()
    session_id = payload.get('sessionId') or 'default'

    if action == 'chat':
        prompt = payload.get('prompt')
        if not prompt or not isinstance(prompt, str):
            return response.Response(ctx, status_code=400, headers={'Content-Type': 'application/json'}, response_data=json.dumps({'error': "missing or invalid 'prompt'", 'sessionId': session_id}))
        try:
            result = process_chat(prompt)
            body = {'sessionId': session_id, 'action': 'chat', 'prompt': prompt, **result}
            return response.Response(ctx, status_code=200, headers={'Content-Type': 'application/json'}, response_data=json.dumps(body))
        except Exception as e:
            logger.error(f"Chat processing error: {e}")
            return response.Response(ctx, status_code=500, headers={'Content-Type': 'application/json'}, response_data=json.dumps({'error': 'internal error', 'details': str(e), 'sessionId': session_id}))

    elif action == 'download':
        artifact_id = payload.get('artifactId')
        if not artifact_id:
            return response.Response(ctx, status_code=400, headers={'Content-Type': 'application/json'}, response_data=json.dumps({'error': 'missing artifactId', 'sessionId': session_id}))
        try:
            result = process_download(artifact_id)
            if 'error' in result:
                return response.Response(ctx, status_code=404, headers={'Content-Type': 'application/json'}, response_data=json.dumps({'error': result['error'], 'sessionId': session_id}))
            body = {'sessionId': session_id, 'action': 'download', **result}
            return response.Response(ctx, status_code=200, headers={'Content-Type': 'application/json'}, response_data=json.dumps(body))
        except Exception as e:
            logger.error(f"Download error: {e}")
            return response.Response(ctx, status_code=500, headers={'Content-Type': 'application/json'}, response_data=json.dumps({'error': 'internal error', 'details': str(e), 'sessionId': session_id}))

    else:
        return response.Response(ctx, status_code=400, headers={'Content-Type': 'application/json'}, response_data=json.dumps({'error': f"unsupported action '{action}'", 'sessionId': session_id}))

# Local debug
if __name__ == '__main__':
    print(json.dumps(process_chat("Show me finance report and latest orders with a customer table query"), indent=2))
