"""
AskMeChatBot Interactive - Dynamic Parameter Collection
Intelligently collects required parameters from users before executing agent calls
Supports all 5 agents: General, Finance, HR, Orders, Reports
"""
from flask import Flask, render_template_string, request, jsonify, send_file, session
import os
import logging
import json
import requests
from datetime import datetime
from typing import Dict, List, Optional, Any
from requests.auth import HTTPBasicAuth
import base64
from io import BytesIO
import re
import time
import uuid
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# OCI SDK imports
try:
    import oci
    from oci.generative_ai_inference import GenerativeAiInferenceClient
    from oci.generative_ai_inference.models import (
        OnDemandServingMode,
        ChatDetails,
        CohereChatRequest
    )
    OCI_AVAILABLE = True
except ImportError as e:
    OCI_AVAILABLE = False
    print(f"OCI SDK not available: {e}")

# Configure logging
logging.basicConfig(
    filename='askme_interactive.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(console_handler)

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Server-side storage for downloads
download_storage = {}

logger.info("AskMeChatBot Interactive initialized")


def load_config():
    """Load configuration from config.properties"""
    config = {}
    config_path = os.path.join(os.path.dirname(__file__), 'config.properties')
    try:
        with open(config_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()
        logger.info(f"Configuration loaded from {config_path}")
    except Exception as e:
        logger.error(f"Error loading config: {e}")
    return config


def load_api_spec(spec_file):
    """Load API specification from JSON file"""
    spec_path = os.path.join(os.path.dirname(__file__), spec_file)
    try:
        with open(spec_path, 'r') as f:
            spec = json.load(f)
            logger.info(f"Loaded API spec: {spec_file}")
            return spec
    except Exception as e:
        logger.warning(f"Could not load {spec_file}: {e}")
        return None


# Load configuration
CONFIG = load_config()
USE_MOCK_RESPONSES = CONFIG.get('use_mock_responses', 'false').lower() == 'true'
API_TIMEOUT = int(CONFIG.get('api_timeout', '30'))
API_RETRY_COUNT = int(CONFIG.get('api_retry_count', '3'))
API_RETRY_DELAY = int(CONFIG.get('api_retry_delay', '1'))
GENAI_INTENT_MODE = CONFIG.get('genai_intent_mode', 'auto').strip().lower()
GENAI_MODEL_ID = 'cohere.command-plus-latest'

# Load API specifications
API_SPEC_GENERAL = load_api_spec('api_spec_general.json')
API_SPEC_FINANCE = load_api_spec('api_spec_finance.json')
API_SPEC_HR = load_api_spec('api_spec_hr.json')
API_SPEC_ORDERS = load_api_spec('api_spec_orders.json')
API_SPEC_REPORTS = load_api_spec('api_spec_reports.json')

logger.info(f"Using mock responses: {USE_MOCK_RESPONSES}")
logger.info(f"Gen AI intent mode: {GENAI_INTENT_MODE}")

# Initialize OCI Gen AI Client
genai_client = None
genai_region = None
if OCI_AVAILABLE:
    try:
        oci_user = os.getenv('OCI_USER')
        oci_key_file = os.getenv('OCI_KEY_FILE')
        oci_fingerprint = os.getenv('OCI_FINGERPRINT')
        oci_tenancy = os.getenv('OCI_TENANCY')
        genai_region = CONFIG.get('genai_region', 'us-chicago-1')
        
        if all([oci_user, oci_key_file, oci_fingerprint, oci_tenancy]):
            if os.path.isabs(oci_key_file):
                key_file_path = oci_key_file
            elif oci_key_file.startswith('~'):
                key_file_path = os.path.expanduser(oci_key_file)
            else:
                key_file_path = os.path.join(os.path.dirname(__file__), oci_key_file)
            
            oci_config = {
                'user': oci_user,
                'key_file': key_file_path,
                'fingerprint': oci_fingerprint,
                'tenancy': oci_tenancy,
                'region': genai_region
            }
            genai_client = GenerativeAiInferenceClient(
                config=oci_config,
                service_endpoint=f"https://inference.generativeai.{genai_region}.oci.oraclecloud.com"
            )
            logger.info(f"OCI Gen AI client initialized for {genai_region}")
        else:
            logger.warning("OCI credentials not found in .env file. Gen AI intent detection will be skipped.")
    except Exception as e:
        logger.error(f"Failed to initialize OCI Gen AI: {e}")
        genai_client = None


def build_agent_parameters_from_specs():
    """Build parameter definitions dynamically from API specs with defaults"""
    params = {}
    
    # Finance - from BI Publisher SOAP spec
    params["finance"] = {
        "required": [],  # All optional with defaults
        "optional": ["po_number", "format"],
        "defaults": {
            "po_number": "55269",  # Default from API spec example
            "format": "pdf",
            "report_path": "/Custom/ROIC/ROIC_PO_REPORTS.xdo"
        },
        "formats": ["pdf", "xls", "html", "xml"],
        "descriptions": {
            "po_number": "Purchase Order Number",
            "format": "Report output format (pdf, xls, html, xml)"
        }
    }
    
    # HR - from ORDS GenAI spec (simple prompt-based)
    params["hr"] = {
        "required": [],
        "optional": [],
        "defaults": {},
        "descriptions": {}
    }
    
    # Orders - from Fusion SCM REST spec
    params["orders"] = {
        "required": [],
        "optional": ["order_key", "limit"],
        "defaults": {
            "limit": 10  # Default from API spec
        },
        "descriptions": {
            "order_key": "Specific Order Key/ID for detail view",
            "limit": "Maximum number of orders to return (default: 10)"
        }
    }
    
    # Reports - from OAC Export spec
    if API_SPEC_REPORTS:
        servers = API_SPEC_REPORTS.get('servers', [])
        default_workbook_id = "L3NoYXJlZC9SQ09FL0Fic2VuY2UgV29ya2Jvb2s"
        default_api_version = "20210901"
        
        if servers and 'variables' in servers[0]:
            vars = servers[0]['variables']
            default_workbook_id = vars.get('instance', {}).get('default', default_workbook_id)
            default_api_version = vars.get('apiVersion', {}).get('default', default_api_version)
        
        params["reports"] = {
            "required": [],
            "optional": ["workbook_id", "format", "canvas_ids"],
            "defaults": {
                "workbook_id": CONFIG.get('reports_workbook_id', default_workbook_id),
                "format": "pdf",
                "api_version": default_api_version,
                "canvas_ids": "snapshot!canvas!1"
            },
            "formats": ["pdf", "png", "xlsx", "csv"],
            "descriptions": {
                "workbook_id": "OAC Workbook ID (Base64 encoded)",
                "format": "Export format (pdf, png, xlsx, csv)",
                "canvas_ids": "Canvas IDs to export (comma-separated)"
            }
        }
    else:
        params["reports"] = {
            "required": [],
            "optional": ["format"],
            "defaults": {"format": "pdf"},
            "formats": ["pdf", "png", "xlsx", "csv"],
            "descriptions": {"format": "Export format"}
        }
    
    # General - no parameters needed
    params["general"] = {
        "required": [],
        "optional": [],
        "defaults": {},
        "descriptions": {}
    }
    
    return params


# Build parameters from API specs
AGENT_PARAMETERS = build_agent_parameters_from_specs()
logger.info("Agent parameters built from API specs")


def detect_intent_with_genai(query: str) -> Optional[str]:
    """Detect intent using OCI Gen AI (matching parent app logic)"""
    if not genai_client:
        return None
    
    try:
        classification_prompt = f"""Classify this query into ONE category: general, finance, hr, orders, reports.

Query: {query}

Return only the category name."""

        chat_request = CohereChatRequest(
            message=classification_prompt,
            max_tokens=10,
            temperature=0.3,
            frequency_penalty=0,
            top_p=0.75,
            top_k=0
        )
        
        chat_details = ChatDetails(
            serving_mode=OnDemandServingMode(model_id=GENAI_MODEL_ID),
            compartment_id=os.getenv('OCI_TENANCY'),
            chat_request=chat_request
        )
        
        logger.info(f"Calling OCI Gen AI for intent detection with model: {GENAI_MODEL_ID}")
        response = genai_client.chat(chat_details)
        
        if response.data and response.data.chat_response:
            intent = response.data.chat_response.text.strip().lower()
            logger.info(f"OCI Gen AI detected intent: {intent}")
            
            valid_intents = ['general', 'finance', 'hr', 'orders', 'reports']
            if intent in valid_intents:
                return intent
            else:
                logger.warning(f"Invalid intent from Gen AI: {intent}")
                return None
        else:
            logger.warning("No response from OCI Gen AI")
            return None
            
    except Exception as e:
        logger.error(f"Error in OCI Gen AI intent detection: {e}")
        return None


def extract_parameters_from_query(query: str, agent_type: str) -> Dict[str, Any]:
    """Extract parameters from natural language query using pattern matching"""
    params = {}
    query_lower = query.lower()
    
    # Get defaults for this agent
    defaults = AGENT_PARAMETERS.get(agent_type, {}).get('defaults', {})
    
    if agent_type == "finance":
        # Extract PO number
        po_match = re.search(r'\b\d{5,6}\b', query)
        if po_match:
            params["po_number"] = po_match.group(0)
        else:
            params["po_number"] = defaults.get("po_number", "55269")
        
        # Extract format
        if "excel" in query_lower or "xls" in query_lower:
            params["format"] = "xls"
        elif "html" in query_lower:
            params["format"] = "html"
        elif "xml" in query_lower:
            params["format"] = "xml"
        else:
            params["format"] = defaults.get("format", "pdf")
        
        params["report_path"] = defaults.get("report_path", "/Custom/ROIC/ROIC_PO_REPORTS.xdo")
    
    elif agent_type == "hr":
        # HR uses simple prompt pass-through to ORDS
        pass
    
    elif agent_type == "orders":
        # Extract order key/number
        order_match = re.search(r'\b[A-Z]{2,10}:\d{9,}\b', query)
        if order_match:
            params["order_key"] = order_match.group(0)
        else:
            # Look for long numeric ID
            order_match2 = re.search(r'\b\d{9,15}\b', query)
            if order_match2:
                params["order_key"] = order_match2.group(0)
        
        # Extract limit - check for "last N", "limit N", etc.
        limit_match = re.search(r'\b(?:last|limit|top|first)\s+(\d+)\b', query_lower)
        if limit_match:
            params["limit"] = int(limit_match.group(1))
        else:
            params["limit"] = defaults.get("limit", 10)
    
    elif agent_type == "reports":
        # Extract workbook ID if specified
        wb_match = re.search(r'\b[A-Za-z0-9+/=]{20,}\b', query)
        if wb_match:
            params["workbook_id"] = wb_match.group(0)
        else:
            params["workbook_id"] = defaults.get("workbook_id")
        
        # Extract format
        if "png" in query_lower:
            params["format"] = "png"
        elif "excel" in query_lower or "xlsx" in query_lower:
            params["format"] = "xlsx"
        elif "csv" in query_lower:
            params["format"] = "csv"
        else:
            params["format"] = defaults.get("format", "pdf")
        
        params["api_version"] = defaults.get("api_version", "20210901")
        params["canvas_ids"] = defaults.get("canvas_ids", "snapshot!canvas!1")
    
    return params


def check_missing_parameters(params: Dict[str, Any], agent_type: str) -> List[str]:
    """Check which required parameters are missing"""
    if agent_type not in AGENT_PARAMETERS:
        return []
    
    required = AGENT_PARAMETERS[agent_type]["required"]
    missing = [p for p in required if p not in params or not params[p]]
    return missing


def execute_finance_agent(params: Dict[str, Any]) -> str:
    """Execute Finance agent - BI Publisher SOAP API (matching parent app)"""
    logger.info(f"Executing Finance agent with params: {params}")
    
    if USE_MOCK_RESPONSES:
        po_number = params.get("po_number", "55269")
        return f"📄 Purchase Order Report for PO #{po_number}\n\nStatus: Approved\nAmount: $45,230.00\nVendor: Oracle Corporation\nDelivery Date: 2025-12-15\n\n(Mock response - set use_mock_responses=false for real API)"
    
    finance_url = CONFIG.get('finance_agent_url')
    finance_username = CONFIG.get('finance_agent_username')
    finance_password = CONFIG.get('finance_agent_password')
    
    if not finance_url:
        logger.warning("Finance agent URL not configured")
        return "Finance report API not configured. Please check config.properties."
    
    if not finance_username or not finance_password:
        logger.warning("Finance agent credentials not configured")
        return "Finance report API credentials not configured. Please check config.properties."
    
    try:
        po_number = params.get("po_number", "55269")
        report_format = params.get("format", "pdf")
        report_path = params.get("report_path", "/Custom/ROIC/ROIC_PO_REPORTS.xdo")
        
        soap_body = f'''<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" xmlns:pub="http://xmlns.oracle.com/oxp/service/PublicReportService">
   <soap:Header/>
   <soap:Body>
      <pub:runReport>
         <pub:reportRequest>
            <pub:attributeFormat>{report_format}</pub:attributeFormat>
            <pub:parameterNameValues>
               <pub:item>
                  <pub:name>P_PO_NUM</pub:name>
                  <pub:values>
                     <pub:item>{po_number}</pub:item>
                  </pub:values>
               </pub:item>
            </pub:parameterNameValues>
            <pub:reportAbsolutePath>{report_path}</pub:reportAbsolutePath>
            <pub:sizeOfDataChunkDownload>-1</pub:sizeOfDataChunkDownload>
         </pub:reportRequest>
         <pub:appParams></pub:appParams>
      </pub:runReport>
   </soap:Body>
</soap:Envelope>'''
        
        headers = {
            "Content-Type": "application/soap+xml; charset=UTF-8",
            "SOAPAction": ""
        }
        
        logger.info(f"Calling Finance BI Publisher SOAP API at {finance_url}")
        logger.info(f"Using PO Number: {po_number}, Format: {report_format}")
        
        auth = HTTPBasicAuth(finance_username, finance_password)
        response = requests.post(
            finance_url,
            data=soap_body,
            headers=headers,
            auth=auth,
            timeout=API_TIMEOUT,
            verify=True
        )
        
        logger.info(f"BI Publisher SOAP API response status: {response.status_code}")
        
        if response.status_code == 200:
            response_text = response.text
            report_bytes_match = re.search(r'<[^:]+:reportBytes>([^<]+)</[^:]+:reportBytes>', response_text)
            
            if report_bytes_match:
                report_bytes = report_bytes_match.group(1).strip()
                logger.info(f"Successfully received base64 report from BI Publisher (length: {len(report_bytes)} chars)")
                return f"PDF_DOWNLOAD:Finance:{report_bytes}"
            else:
                logger.warning("No reportBytes found in SOAP response")
                return "Report generated but PDF data not found in SOAP response."
        elif response.status_code == 401:
            logger.error(f"Finance BI Publisher SOAP API authentication failed (401)")
            return "Finance report API authentication failed. Please verify username and password in config.properties."
        else:
            logger.warning(f"Finance BI Publisher SOAP API returned status {response.status_code}")
            return f"Finance report API error: HTTP {response.status_code}"
            
    except requests.exceptions.Timeout:
        logger.error(f"Finance BI Publisher SOAP API timeout after {API_TIMEOUT}s")
        return "Finance report API timeout. Please try again."
    except requests.exceptions.RequestException as e:
        logger.error(f"Finance BI Publisher SOAP API error: {str(e)}")
        return f"Finance report API error: {str(e)}"
    except Exception as e:
        logger.error(f"Finance BI Publisher SOAP unexpected error: {str(e)}")
        return f"Finance report error: {str(e)}"


def execute_hr_agent(query: str) -> str:
    """Execute HR agent - ORDS GenAI Module (matching parent app)"""
    logger.info(f"Executing HR agent with query: {query}")
    
    if USE_MOCK_RESPONSES:
        query_lower = query.lower()
        if "policy" in query_lower or "policies" in query_lower:
            return "📋 Our work-from-home policy allows 3 days remote work per week with core hours from 10 AM to 4 PM."
        elif "benefit" in query_lower:
            return "🎁 Employee benefits include comprehensive health insurance, 401k matching up to 6%, and annual learning allowance."
        elif "leave" in query_lower:
            return "🏖️ Annual leave policy includes 20 days PTO, 10 sick days, and additional floating holidays."
        else:
            return "HR information is available. Please specify: policy, benefits, or leave."
    
    hr_url = CONFIG.get('hr_agent_url')
    hr_username = CONFIG.get('hr_agent_username')
    hr_password = CONFIG.get('hr_agent_password')
    
    if not hr_url:
        logger.warning("HR agent URL not configured, using mock response")
        return "HR policy information includes work-from-home, benefits, and leave details."
    
    try:
        params = {"prompt": query}
        headers = {"Accept": "application/json"}
        auth = HTTPBasicAuth(hr_username, hr_password) if hr_username else None
        
        logger.info(f"Calling HR ORDS API: {hr_url}")
        resp = requests.get(hr_url, params=params, headers=headers, auth=auth, timeout=API_TIMEOUT)
        
        if resp.status_code == 200:
            data = resp.json()
            
            # Handle array results (tabular records)
            if isinstance(data, list) and len(data) > 0:
                top_items = data[:10]
                formatted = []
                for idx, item in enumerate(top_items, 1):
                    item_str = f"{idx}. " + ", ".join([f"{k}: {v}" for k, v in item.items()])
                    formatted.append(item_str)
                result_text = "\n".join(formatted)
                if len(data) > 10:
                    result_text += f"\n\n💡 Showing first 10 of {len(data)} records."
                return result_text
            
            # Handle object with known fields
            result = data.get('query_result', data.get('response', data.get('reply', data.get('answer'))))
            if result:
                logger.info("HR API call successful")
                return result
            
            return "HR agent did not return content for this query."
        else:
            logger.warning(f"HR API returned {resp.status_code}")
            return "HR agent API unavailable. Please try again later."
            
    except Exception as e:
        logger.error(f"HR agent error: {e}")
        return f"HR agent error: {str(e)}"


def execute_orders_agent(params: Dict[str, Any]) -> str:
    """Execute Orders agent - Fusion SCM REST API (matching parent app)"""
    logger.info(f"Executing Orders agent with params: {params}")
    
    if USE_MOCK_RESPONSES:
        order_key = params.get("order_key")
        if order_key:
            return f"📦 Order Details - {order_key}\n\nStatus: Shipped\nCustomer: Acme Corp\nItems: 5\nTotal: $12,450.00\nEstimated Delivery: 2025-12-08\n\n(Mock response)"
        else:
            return "📋 Recent Orders:\n\n• ORD-100234 | Status: Shipped\n• ORD-100235 | Status: Processing\n• ORD-100236 | Status: Delivered\n• ORD-100237 | Status: Pending\n• ORD-100238 | Status: Shipped\n\n(Mock response)"
    
    orders_url = CONFIG.get('orders_agent_url')
    orders_username = CONFIG.get('orders_agent_username')
    orders_password = CONFIG.get('orders_agent_password')
    
    if not orders_url:
        logger.warning("Orders agent URL not configured")
        return "Orders API not configured."
    
    if not orders_username or not orders_password:
        logger.warning("Orders agent credentials not configured")
        return "Orders API credentials not configured."
    
    order_key = params.get("order_key")
    headers = {"Accept": "application/json"}
    auth = HTTPBasicAuth(orders_username, orders_password)
    
    try:
        if order_key:
            # Fetch specific order detail
            url = f"{orders_url}/{order_key}"
            logger.info(f"Calling Orders API (detail) at {url}")
            resp = requests.get(url, headers=headers, auth=auth, timeout=API_TIMEOUT, verify=True)
            logger.info(f"Orders detail response status: {resp.status_code}")
            
            if resp.status_code == 200:
                data = resp.json()
                ok = data.get('OrderKey', order_key)
                status = data.get('StatusCode', 'N/A')
                submitted_by = data.get('SubmittedBy', 'N/A')
                submitted_date = data.get('SubmittedDate', 'N/A')
                lines = data.get('lines') or []
                
                line_summaries = []
                for ln in lines[:5]:
                    ln_num = ln.get('LineNumber')
                    item = ln.get('ItemNumber')
                    qty = ln.get('OrderedQuantity')
                    line_summaries.append(f"Line {ln_num}: {item} x{qty}")
                
                lines_text = "\n".join(line_summaries) if line_summaries else "(No line details returned)"
                return (
                    f"📦 Order {ok}\n"
                    f"Status: {status}\n"
                    f"Submitted By: {submitted_by} on {submitted_date}\n\n"
                    f"Top Lines:\n{lines_text}"
                )
            elif resp.status_code == 404:
                return f"No sales order found for key/id '{order_key}'."
            elif resp.status_code == 401:
                logger.error("Orders API authentication failed (401)")
                return "Orders API authentication failed. Please verify username/password."
            else:
                logger.warning(f"Orders detail API returned {resp.status_code}")
                return f"Orders API error: HTTP {resp.status_code}"
        else:
            # Fetch list of orders
            limit = params.get("limit", 10)
            request_params = {"limit": limit}
            logger.info(f"Calling Orders API (list, limit={limit}) at {orders_url}")
            resp = requests.get(orders_url, params=request_params, headers=headers, auth=auth, timeout=API_TIMEOUT, verify=True)
            logger.info(f"Orders list response status: {resp.status_code}")
            
            if resp.status_code == 200:
                data = resp.json()
                items = data.get('items') or []
                if not items:
                    return "No recent sales orders were returned by the API."
                
                # Sort by LastUpdateDate descending
                def _parse_dt(s):
                    try:
                        return datetime.fromisoformat(s.replace('Z', '+00:00')) if isinstance(s, str) else datetime.min
                    except Exception:
                        return datetime.min
                
                items_sorted = sorted(items, key=lambda it: _parse_dt(it.get('LastUpdateDate')), reverse=True)
                display_items = items_sorted[:10]
                total_count = len(items_sorted)
                
                lines = []
                for it in display_items:
                    ok = it.get('OrderKey', 'N/A')
                    status = it.get('StatusCode', 'N/A')
                    created_by = it.get('CreatedBy', 'N/A')
                    last_upd = it.get('LastUpdateDate', 'N/A')
                    lines.append(f"• {ok} | Status: {status} | By: {created_by} | Updated: {last_upd}")
                
                result_text = f"📋 Recent Sales Orders (showing 10 of {total_count}):\n" + "\n".join(lines)
                if total_count > 10:
                    result_text += "\n\n💡 Showing first 10 orders. Use specific Order ID for details."
                
                return result_text
            elif resp.status_code == 401:
                logger.error("Orders API authentication failed (401)")
                return "Orders API authentication failed. Please verify username/password."
            else:
                logger.warning(f"Orders list API returned {resp.status_code}")
                return f"Orders API error: HTTP {resp.status_code}"
                
    except requests.exceptions.Timeout:
        logger.error(f"Orders API timeout after {API_TIMEOUT}s")
        return "Orders API timeout. Please try again."
    except requests.exceptions.RequestException as e:
        logger.error(f"Orders API error: {str(e)}")
        return f"Orders API error: {str(e)}"
    except Exception as e:
        logger.error(f"Orders advisor unexpected error: {str(e)}")
        return f"Orders API error: {str(e)}"


def execute_reports_agent(params: Dict[str, Any]) -> str:
    """Execute Reports agent - OAC Export API (matching parent app)"""
    logger.info(f"Executing Reports agent with params: {params}")
    
    export_format = params.get("format", "pdf")
    
    if USE_MOCK_RESPONSES:
        return f"📊 Workbook Export ({export_format.upper()})\n\nExport completed successfully.\nFormat: {export_format.upper()}\nSize: 2.4 MB\n\n(Mock response)"
    
    reports_url = CONFIG.get('reports_agent_url')
    reports_username = CONFIG.get('reports_agent_username')
    reports_password = CONFIG.get('reports_agent_password')
    
    if not reports_url:
        logger.warning("Reports agent URL not configured")
        return "Reports API not configured. Please check config.properties."
    
    if not reports_username or not reports_password:
        logger.warning("Reports agent credentials not configured")
        return "Reports API credentials not configured. Please check config.properties."
    
    try:
        api_version = params.get("api_version", "20210901")
        workbook_id = params.get("workbook_id", CONFIG.get('reports_workbook_id', 'L3NoYXJlZC9SQ09FL0Fic2VuY2UgV29ya2Jvb2s'))
        canvas_ids = params.get("canvas_ids", "snapshot!canvas!1").split(",")
        
        export_url = f"{reports_url}/api/{api_version}/catalog/workbooks/{workbook_id}/exports"
        payload = {
            "name": "Absence Workbook Report",
            "type": "file",
            "canvasIds": canvas_ids,
            "format": export_format,
            "screenwidth": 1440,
            "screenheight": 900
        }
        
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        auth = HTTPBasicAuth(reports_username, reports_password)
        
        logger.info(f"Calling Reports API (export) at {export_url}")
        logger.debug(f"Request payload: {json.dumps(payload, indent=2)}")
        resp = requests.post(export_url, json=payload, headers=headers, auth=auth, timeout=API_TIMEOUT, verify=True)
        logger.info(f"Reports export response status: {resp.status_code}")
        
        if resp.status_code not in (200, 201, 202):
            logger.warning(f"Reports export API returned {resp.status_code}: {resp.text[:300]}")
            if resp.status_code == 401:
                return "Reports API authentication failed. Please verify username/password in config.properties."
            return f"Reports export API error: HTTP {resp.status_code}"
        
        export_data = {}
        try:
            export_data = resp.json()
        except Exception:
            logger.warning("Export response not JSON parseable; attempting resourceUri extraction from text")
        
        resource_uri = export_data.get('resourceUri') if isinstance(export_data, dict) else None
        export_id = None
        if resource_uri and '/exports/' in resource_uri:
            export_id = resource_uri.split('/exports/')[-1]
            logger.info(f"Parsed exportId from resourceUri: {export_id}")
        else:
            export_id = export_data.get('exportId') if isinstance(export_data, dict) else None
            if export_id:
                logger.info(f"Found exportId field: {export_id}")
        
        if not export_id:
            logger.error(f"No exportId derivable from response: {export_data}")
            return "Reports API did not return an export ID."
        
        logger.info(f"Export initiated with ID: {export_id}")
        
        # Wait 30 seconds then attempt download directly (no status check), retry up to 3 times
        logger.info("Waiting 30s before attempting download to allow export job to complete")
        time.sleep(30)
        
        download_url = f"{reports_url}/api/{api_version}/catalog/workbooks/{workbook_id}/exports/{export_id}"
        max_attempts = 3
        download_resp = None
        
        for attempt in range(max_attempts):
            logger.info(f"Download attempt {attempt + 1}/{max_attempts} from {download_url}")
            try:
                download_resp = requests.get(download_url, auth=auth, timeout=API_TIMEOUT, verify=True)
                logger.info(f"Download response status: {download_resp.status_code}")
                
                if download_resp.status_code == 200:
                    logger.info("Download successful")
                    break
                else:
                    logger.warning(f"Download attempt {attempt + 1} failed with {download_resp.status_code}: {download_resp.text[:300]}")
                    if attempt < max_attempts - 1:
                        logger.info("Waiting 10s before retry")
                        time.sleep(10)
            except requests.exceptions.Timeout:
                logger.warning(f"Download attempt {attempt + 1} timed out")
                if attempt < max_attempts - 1:
                    logger.info("Waiting 10s before retry")
                    time.sleep(10)
        
        if not download_resp or download_resp.status_code != 200:
            logger.error("Download failed after all retry attempts")
            return "Reports download failed after retries. Please try again later."
        
        report_bytes_b64 = base64.b64encode(download_resp.content).decode('utf-8')
        logger.info(f"Successfully downloaded report (size: {len(download_resp.content)} bytes, base64 length: {len(report_bytes_b64)} chars)")
        return f"REPORT_DOWNLOAD:Reports:{export_format.upper()}:{report_bytes_b64}"
        
    except requests.exceptions.Timeout:
        logger.error(f"Reports API timeout after {API_TIMEOUT}s")
        return "Reports API timeout. Please try again."
    except requests.exceptions.RequestException as e:
        logger.error(f"Reports API error: {str(e)}")
        return f"Reports API error: {str(e)}"
    except json.JSONDecodeError as e:
        logger.error(f"Reports API JSON decode error: {str(e)}")
        return "Reports API returned invalid response."
    except Exception as e:
        logger.error(f"Reports advisor unexpected error: {str(e)}")
        return f"Reports API error: {str(e)}"


def execute_general_agent(query: str) -> str:
    """Execute General agent"""
    logger.info(f"Executing General agent with query: {query}")
    
    query_lower = query.lower()
    
    # Check for help/capabilities keywords
    if "help" in query_lower or "what can you do" in query_lower:
        return "🤖 I'm your General Assistant!\n\nI can help you with:\n• Finance - Reports and financial data\n• HR - Policies and employee info\n• Orders - Sales order management\n• Reports - Analytics and exports\n\nJust ask me anything and I'll collect the details I need!"
    
    if "capabilities" in query_lower:
        return "✨ My Capabilities:\n\n• Intelligent intent detection\n• Dynamic parameter collection\n• Multi-agent orchestration\n• Real-time data retrieval\n• Document generation"
    
    # Call ORDS GenAI Module for NL2SQL or general knowledge
    general_url = CONFIG.get('general_agent_url')
    if general_url and not USE_MOCK_RESPONSES:
        try:
            response = requests.get(general_url, params={"prompt": query}, timeout=API_TIMEOUT)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    result = "\n".join([f"{i+1}. {item}" for i, item in enumerate(data[:10])])
                    if len(data) > 10:
                        result += f"\n\n💡 Showing 10 of {len(data)} records"
                    return result
                return data.get('query_result', "General query processed.")
        except Exception as e:
            logger.error(f"General agent error: {e}")
    
    return "I'm here to help! Please specify what you'd like to know about Finance, HR, Orders, or Reports."


# HTML Template with interactive parameter collection
template = r"""
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>AskMe ChatBot Interactive</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; justify-content: center; align-items: center; padding: 20px; }
        .container { background: white; border-radius: 20px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); width: 100%; max-width: 900px; height: 90vh; display: flex; flex-direction: column; overflow: hidden; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 25px; text-align: center; }
        .header h1 { font-size: 28px; margin-bottom: 5px; }
        .header p { font-size: 14px; opacity: 0.9; }
        .chat-box { flex: 1; overflow-y: auto; padding: 20px; background: #f8f9fa; }
        .message { margin-bottom: 15px; display: flex; align-items: flex-start; animation: fadeIn 0.3s; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .message.user { justify-content: flex-end; }
        .message-content { max-width: 70%; padding: 12px 16px; border-radius: 18px; word-wrap: break-word; }
        .message.user .message-content { background: #667eea; color: white; border-bottom-right-radius: 4px; }
        .message.bot .message-content { background: white; color: #333; border-bottom-left-radius: 4px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        .advisor-name { font-weight: bold; color: #667eea; margin-bottom: 5px; font-size: 14px; }
        .param-form { background: #fff3cd; border: 2px solid #ffc107; border-radius: 12px; padding: 15px; margin: 10px 0; }
        .param-form h4 { color: #856404; margin-bottom: 10px; }
        .param-input { margin: 8px 0; }
        .param-input label { display: block; font-size: 13px; color: #856404; margin-bottom: 4px; font-weight: 500; }
        .param-input input, .param-input select { width: 100%; padding: 8px; border: 1px solid #ffc107; border-radius: 6px; font-size: 14px; }
        .param-submit { background: #ffc107; color: #856404; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-weight: bold; margin-top: 10px; }
        .param-submit:hover { background: #e0a800; }
        .download-btn { display: inline-block; background: #28a745; color: white; padding: 10px 20px; border-radius: 8px; text-decoration: none; margin-top: 10px; font-size: 14px; }
        .download-btn:hover { background: #218838; }
        .input-area { padding: 20px; background: white; border-top: 1px solid #dee2e6; }
        .input-group { display: flex; gap: 10px; }
        .input-group input { flex: 1; padding: 12px; border: 2px solid #667eea; border-radius: 25px; font-size: 15px; outline: none; }
        .input-group button { background: #667eea; color: white; border: none; padding: 12px 30px; border-radius: 25px; cursor: pointer; font-size: 15px; font-weight: bold; transition: all 0.3s; }
        .input-group button:hover { background: #5568d3; transform: scale(1.05); }
        .sample-prompts { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 15px; }
        .sample-btn { background: #e9ecef; border: 1px solid #dee2e6; padding: 8px 16px; border-radius: 20px; cursor: pointer; font-size: 13px; transition: all 0.2s; }
        .sample-btn:hover { background: #667eea; color: white; border-color: #667eea; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 AskMe ChatBot Interactive</h1>
            <p>Intelligent Multi-Agent System with Dynamic Parameter Collection</p>
        </div>
        <div class="chat-box" id="chatBox">
            <div class="message bot">
                <div class="message-content">
                    <div class="advisor-name">🤖 General Agent</div>
                    Welcome! I'm your intelligent assistant with 5 specialized agents.<br><br>
                    I'll automatically detect what you need and ask for any required details!<br><br>
                    Try asking about Finance, HR, Orders, Reports, or General help.
                </div>
            </div>
        </div>
        <div class="input-area">
            <div class="sample-prompts">
                <button class="sample-btn" onclick="setPrompt('Generate purchase order report for PO 55269')">📄 Finance Report</button>
                <button class="sample-btn" onclick="setPrompt('Show HR leave policy')">👥 HR Policy</button>
                <button class="sample-btn" onclick="setPrompt('List recent orders')">📦 Recent Orders</button>
                <button class="sample-btn" onclick="setPrompt('Export workbook as PDF')">📊 Export Report</button>
                <button class="sample-btn" onclick="setPrompt('What can you help me with?')">❓ Help</button>
            </div>
            <div class="input-group">
                <input type="text" id="userInput" placeholder="Ask me anything..." onkeypress="if(event.key==='Enter') sendMessage()">
                <button onclick="sendMessage()">Send</button>
            </div>
        </div>
    </div>

    <script>
        let currentContext = {};

        function setPrompt(text) {
            document.getElementById('userInput').value = text;
            document.getElementById('userInput').focus();
        }

        function addMessage(content, isUser = false, advisorName = null) {
            const chatBox = document.getElementById('chatBox');
            const messageDiv = document.createElement('div');
            messageDiv.className = 'message ' + (isUser ? 'user' : 'bot');
            
            const contentDiv = document.createElement('div');
            contentDiv.className = 'message-content';
            
            if (advisorName && !isUser) {
                const nameDiv = document.createElement('div');
                nameDiv.className = 'advisor-name';
                nameDiv.textContent = advisorName;
                contentDiv.appendChild(nameDiv);
            }
            
            const textDiv = document.createElement('div');
            textDiv.innerHTML = content.replace(/\n/g, '<br>');
            contentDiv.appendChild(textDiv);
            
            messageDiv.appendChild(contentDiv);
            chatBox.appendChild(messageDiv);
            chatBox.scrollTop = chatBox.scrollHeight;
        }

        function addParameterForm(params, agentType) {
            const chatBox = document.getElementById('chatBox');
            const formDiv = document.createElement('div');
            formDiv.className = 'message bot';
            
            const contentDiv = document.createElement('div');
            contentDiv.className = 'message-content';
            
            let formHtml = '<div class="param-form"><h4>📝 Please provide the following details:</h4>';
            
            params.missing.forEach(param => {
                const desc = params.descriptions[param];
                formHtml += `<div class="param-input">
                    <label>${desc}:</label>`;
                
                if (param === 'report_type' || param === 'query_type' || param === 'export_type') {
                    const options = param === 'report_type' ? params.report_types :
                                   param === 'query_type' ? params.query_types :
                                   params.export_types;
                    formHtml += `<select id="param_${param}">`;
                    options.forEach(opt => {
                        formHtml += `<option value="${opt}">${opt.replace('_', ' ')}</option>`;
                    });
                    formHtml += `</select>`;
                } else if (param === 'format') {
                    formHtml += `<select id="param_${param}">`;
                    params.formats.forEach(fmt => {
                        formHtml += `<option value="${fmt}">${fmt.toUpperCase()}</option>`;
                    });
                    formHtml += `</select>`;
                } else {
                    formHtml += `<input type="text" id="param_${param}" placeholder="Enter ${param.replace('_', ' ')}">`;
                }
                
                formHtml += `</div>`;
            });
            
            formHtml += `<button class="param-submit" onclick="submitParameters('${agentType}', ${JSON.stringify(params.missing).replace(/"/g, '&quot;')})">Submit</button></div>`;
            
            contentDiv.innerHTML = formHtml;
            formDiv.appendChild(contentDiv);
            chatBox.appendChild(formDiv);
            chatBox.scrollTop = chatBox.scrollHeight;
        }

        async function submitParameters(agentType, missingParams) {
            const params = { agent_type: agentType };
            
            missingParams.forEach(param => {
                const value = document.getElementById('param_' + param).value;
                if (value) params[param] = value;
            });
            
            // Merge with current context
            Object.assign(currentContext, params);
            
            addMessage('✅ Parameters submitted', true);
            
            const response = await fetch('/execute', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(currentContext)
            });
            
            const data = await response.json();
            
            if (data.response) {
                if (data.response.startsWith('REPORT_DOWNLOAD:')) {
                    const parts = data.response.split(':');
                    const advisor = parts[1];
                    const format = parts[2];
                    const downloadUrl = data.download_url;
                    
                    addMessage(
                        `Report generated successfully!<br><a href="${downloadUrl}" class="download-btn" download>📥 Download ${format} Report</a>`,
                        false,
                        `${advisor} Advisor`
                    );
                } else {
                    addMessage(data.response, false, data.advisor);
                }
            }
            
            currentContext = {};
        }

        async function sendMessage() {
            const input = document.getElementById('userInput');
            const message = input.value.trim();
            if (!message) return;
            
            addMessage(message, true);
            input.value = '';
            currentContext = { query: message };
            
            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt: message })
            });
            
            const data = await response.json();
            
            if (data.need_params) {
                addParameterForm(data.params, data.agent_type);
                currentContext.agent_type = data.agent_type;
            } else if (data.response) {
                if (data.response.startsWith('REPORT_DOWNLOAD:')) {
                    const parts = data.response.split(':');
                    const advisor = parts[1];
                    const format = parts[2];
                    const downloadUrl = data.download_url;
                    
                    addMessage(
                        `Report generated successfully!<br><a href="${downloadUrl}" class="download-btn" download>📥 Download ${format} Report</a>`,
                        false,
                        `${advisor} Advisor`
                    );
                } else {
                    addMessage(data.response, false, data.advisor);
                }
            }
        }
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    return render_template_string(template)


@app.route('/chat', methods=['POST'])
def chat():
    """Process user query and determine if parameters are needed"""
    data = request.json
    prompt = data.get('prompt', '')
    
    logger.info(f"Received query: {prompt}")
    
    # Store query in session for agents that need it (like HR)
    session['last_query'] = prompt
    
    # Step 1: Detect intent
    intent = None
    if genai_client and GENAI_INTENT_MODE != 'off':
        intent = detect_intent_with_genai(prompt)
    
    # Fallback to keyword detection
    if not intent:
        prompt_lower = prompt.lower()
        if any(kw in prompt_lower for kw in ['finance', 'revenue', 'budget', 'expense', 'po', 'purchase order']):
            intent = 'finance'
        elif any(kw in prompt_lower for kw in ['hr', 'policy', 'benefit', 'leave', 'employee']):
            intent = 'hr'
        elif any(kw in prompt_lower for kw in ['order', 'inventory', 'delivery', 'sales']):
            intent = 'orders'
        elif any(kw in prompt_lower for kw in ['workbook', 'export', 'analytics', 'report', 'dashboard']):
            intent = 'reports'
        else:
            intent = 'general'
    
    logger.info(f"Detected intent: {intent}")
    
    # Step 2: For general agent, execute immediately
    if intent == 'general':
        response = execute_general_agent(prompt)
        return jsonify({
            'response': response,
            'advisor': '🤖 General Agent',
            'need_params': False
        })
    
    # Step 3: Extract parameters from query
    extracted_params = extract_parameters_from_query(prompt, intent)
    missing_params = check_missing_parameters(extracted_params, intent)
    
    logger.info(f"Extracted params: {extracted_params}")
    logger.info(f"Missing params: {missing_params}")
    
    # Step 4: If parameters are missing, request them
    if missing_params:
        param_info = AGENT_PARAMETERS[intent].copy()
        param_info['missing'] = missing_params
        
        return jsonify({
            'need_params': True,
            'agent_type': intent,
            'params': param_info
        })
    
    # Step 5: Execute agent with collected parameters
    session['agent_params'] = extracted_params
    return execute_agent(intent, extracted_params)


@app.route('/execute', methods=['POST'])
def execute():
    """Execute agent with user-provided parameters"""
    data = request.json
    agent_type = data.pop('agent_type', None)
    
    if not agent_type:
        return jsonify({'error': 'No agent type specified'})
    
    logger.info(f"Executing {agent_type} agent with params: {data}")
    return execute_agent(agent_type, data)


def execute_agent(agent_type: str, params: Dict[str, Any]):
    """Execute the appropriate agent with parameters"""
    advisor_icons = {
        'finance': '💰 Finance Advisor',
        'hr': '👥 HR Advisor',
        'orders': '📦 Orders Advisor',
        'reports': '📊 Reports Advisor',
        'general': '🤖 General Agent'
    }
    
    if agent_type == 'finance':
        response = execute_finance_agent(params)
    elif agent_type == 'hr':
        # HR agent uses the original query for ORDS prompt
        query = session.get('last_query', params.get('query', ''))
        response = execute_hr_agent(query)
    elif agent_type == 'orders':
        response = execute_orders_agent(params)
    elif agent_type == 'reports':
        response = execute_reports_agent(params)
    else:
        response = execute_general_agent(params.get('query', ''))
    
    # Handle download responses
    if response.startswith('REPORT_DOWNLOAD:'):
        parts = response.split(':')
        advisor = parts[1]
        file_format = parts[2]
        base64_data = parts[3]
        
        download_id = str(uuid.uuid4())
        download_storage[download_id] = {
            'data': base64_data,
            'filename': f'{advisor}_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.{file_format.lower()}',
            'mimetype': 'application/pdf' if file_format == 'PDF' else f'image/{file_format.lower()}'
        }
        
        return jsonify({
            'response': response,
            'advisor': advisor_icons.get(agent_type, agent_type),
            'download_url': f'/download/{download_id}'
        })
    
    return jsonify({
        'response': response,
        'advisor': advisor_icons.get(agent_type, agent_type),
        'need_params': False
    })


@app.route('/download/<download_id>')
def download(download_id):
    """Serve downloaded files"""
    if download_id not in download_storage:
        return "Download not found", 404
    
    file_data = download_storage[download_id]
    file_bytes = base64.b64decode(file_data['data'])
    
    return send_file(
        BytesIO(file_bytes),
        mimetype=file_data['mimetype'],
        as_attachment=True,
        download_name=file_data['filename']
    )


if __name__ == '__main__':
    logger.info("Starting AskMeChatBot Interactive on http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
