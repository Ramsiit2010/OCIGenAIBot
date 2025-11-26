from flask import Flask, render_template_string, request, jsonify, send_file
import os
import logging
import json
import requests
from datetime import datetime
from typing import Dict
from requests.auth import HTTPBasicAuth
import base64
from io import BytesIO
import re
import time
import uuid
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# OCI SDK imports
try:
    import oci
    from oci.generative_ai_inference import GenerativeAiInferenceClient
    from oci.generative_ai_inference.models import (
        OnDemandServingMode,
        ChatDetails,
        CohereChatRequest,
        CohereMessage
    )
    OCI_AVAILABLE = True
    logger_temp = logging.getLogger(__name__)
    logger_temp.info("OCI SDK loaded successfully")
except ImportError as e:
    OCI_AVAILABLE = False
    logger_temp = logging.getLogger(__name__)
    logger_temp.warning(f"OCI SDK not available: {e}. Install with: pip install oci")

# Configure logging
logging.basicConfig(
    filename='app.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Create console handler for debugging
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Server-side storage for large data (PDFs, reports) to avoid session cookie size limits
download_storage = {}

logger.info("Application initialized")

# Load configuration from properties file
def load_config():
    """Load configuration from config.properties file"""
    config = {}
    config_path = os.path.join(os.path.dirname(__file__), 'config.properties')
    
    try:
        with open(config_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        config[key.strip()] = value.strip()
        logger.info(f"Configuration loaded successfully from {config_path}")
    except FileNotFoundError:
        logger.warning(f"Config file not found at {config_path}, using defaults")
    except Exception as e:
        logger.error(f"Error loading config: {str(e)}")
    
    return config

# Load API specifications
def load_api_spec(spec_file):
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
        logger.error(f"Error loading API spec {spec_file}: {str(e)}")
        return None

# Load configuration
CONFIG = load_config()

# Initialize OCI Gen AI Client
genai_client = None
genai_region = None
if OCI_AVAILABLE:
    try:
        # Read OCI config from environment variables
        oci_user = os.getenv('OCI_USER')
        oci_key_file = os.getenv('OCI_KEY_FILE')
        oci_fingerprint = os.getenv('OCI_FINGERPRINT')
        oci_tenancy = os.getenv('OCI_TENANCY')
        genai_region = CONFIG.get('genai_region', 'us-chicago-1')
        
        if oci_user and oci_key_file and oci_fingerprint and oci_tenancy:
            # Resolve key file path - support both absolute and relative paths
            if os.path.isabs(oci_key_file):
                key_file_path = oci_key_file
            elif oci_key_file.startswith('~'):
                key_file_path = os.path.expanduser(oci_key_file)
            else:
                # Relative path - resolve from project directory
                key_file_path = os.path.join(os.path.dirname(__file__), oci_key_file)
            
            # Create OCI config
            oci_config = {
                'user': oci_user,
                'key_file': key_file_path,
                'fingerprint': oci_fingerprint,
                'tenancy': oci_tenancy,
                'region': genai_region
            }
            
            # Initialize Gen AI client
            genai_client = GenerativeAiInferenceClient(
                config=oci_config,
                service_endpoint=f"https://inference.generativeai.{genai_region}.oci.oraclecloud.com"
            )
            logger.info(f"OCI Gen AI client initialized successfully for {genai_region}")
        else:
            logger.warning("OCI credentials not found in .env file. Gen AI intent detection will be skipped.")
    except Exception as e:
        logger.error(f"Failed to initialize OCI Gen AI client: {e}")
        genai_client = None

# Load API specifications (recommended for production flexibility)
API_SPEC_GENERAL = load_api_spec('api_spec_general.json')
API_SPEC_FINANCE = load_api_spec('api_spec_finance.json')
API_SPEC_HR = load_api_spec('api_spec_hr.json')
API_SPEC_ORDERS = load_api_spec('api_spec_orders.json')
API_SPEC_REPORTS = load_api_spec('api_spec_reports.json')

# Configuration values
USE_MOCK_RESPONSES = CONFIG.get('use_mock_responses', 'true').lower() == 'true'
API_TIMEOUT = int(CONFIG.get('api_timeout', '30'))
API_RETRY_COUNT = int(CONFIG.get('api_retry_count', '3'))
API_RETRY_DELAY = int(CONFIG.get('api_retry_delay', '1'))  # seconds between retries

logger.info(f"Using mock responses: {USE_MOCK_RESPONSES}")
logger.info(f"API retry count: {API_RETRY_COUNT}, delay: {API_RETRY_DELAY}s")

# Gen AI intent routing mode: 'auto' (default), 'force', or 'off'
GENAI_INTENT_MODE = CONFIG.get('genai_intent_mode', 'auto').strip().lower()
logger.info(f"Gen AI intent routing mode: {GENAI_INTENT_MODE}")

# Gen AI model configuration
GENAI_MODEL_ID = 'cohere.command-plus-latest'
logger.info(f"Gen AI model: {GENAI_MODEL_ID}")

# Mock responses from sub-agents
MOCK_RESPONSES = {
    "general": {
        "help": "I am a General Agent that can assist you with Finance, HR, or Orders queries. I can route your questions to specialized advisors or provide general information.",
        "capabilities": "I can help you with:\n• Financial queries (revenue, budgets, expenses)\n• HR policies (benefits, leave, work policies)\n• Order management (status, inventory, returns)\n• General information and routing",
        "services": "Our advisory system provides specialized assistance through dedicated agents for Finance, HR, and Orders. Ask me anything and I'll connect you with the right expert.",
    },
    "finance": {
        "revenue": "Based on our financial analysis, the Q3 revenue shows a 15% increase YoY with strong performance in APAC region.",
        "expenses": "Current expense trends indicate a 10% reduction in operational costs due to automation initiatives.",
        "budget": "The annual budget allocation shows 40% for R&D, 30% for Operations, and 30% for Marketing.",
    },
    "hr": {
        "policy": "Our work-from-home policy allows 3 days remote work per week with core hours from 10 AM to 4 PM.",
        "benefits": "Employee benefits include comprehensive health insurance, 401k matching up to 6%, and annual learning allowance.",
        "leave": "Annual leave policy includes 20 days PTO, 10 sick days, and additional floating holidays.",
    },
    "orders": {
        "status": "Current order fulfillment rate is at 95% with average delivery time of 2.3 days.",
        "inventory": "Warehouse inventory levels are optimal with 98% stock availability.",
        "returns": "Return rate is below industry average at 2.3% with high customer satisfaction.",
    },
    "reports": {
        "workbook": "Your OAC workbook export is being prepared. This typically takes a few moments.",
        "analytics": "Analytics workbook export service is ready. Request a report and I'll generate it for you.",
        "export": "Workbook export completed successfully. Download is ready.",
    }
}

# Helper functions for each advisor
def call_agent_api(agent_type: str, query: str) -> str:
    """
    Call the OCI Gen AI agent API endpoint
    Uses GET method with query parameter as per OCI Gen AI  API spec
    For now, returns mock responses until API is properly configured
    """
    agent_url_key = f"{agent_type}_agent_url"
    agent_user_key = f"{agent_type}_agent_username"
    agent_pass_key = f"{agent_type}_agent_password"
    
    agent_url = CONFIG.get(agent_url_key)
    agent_username = CONFIG.get(agent_user_key)
    agent_password = CONFIG.get(agent_pass_key)
    
    # If using mock responses or API not configured, return mock response
    if USE_MOCK_RESPONSES or not agent_url:
        logger.info(f"{agent_type.capitalize()} agent using mock response (USE_MOCK_RESPONSES={USE_MOCK_RESPONSES})")
        return None  # Return None to fall back to mock logic
    
    # Prepare API request for OCI Gen AI  (GET with query parameter)
    try:
        # OCI Gen AI  API uses GET method with 'prompt' as query parameter
        params = {
            "prompt": query
        }
        
        headers = {
            "Accept": "application/json"
        }
        
        logger.info(f"Calling {agent_type} agent OCI Gen AI  API at {agent_url}")
        logger.debug(f"Query: {query}")
        
        # Make API call with authentication (if provided)
        auth = HTTPBasicAuth(agent_username, agent_password) if agent_username and agent_password else None
        
        response = requests.get(
            agent_url,
            params=params,
            headers=headers,
            auth=auth,
            timeout=API_TIMEOUT
        )
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"{agent_type.capitalize()} agent API call successful")
            
            # Check if result is a list/array (ORDS might return array of items)
            if isinstance(result, list):
                total_count = len(result)
                if total_count > 10:
                    # Paginate: show first 10 items
                    display_items = result[:10]
                    formatted_items = []
                    for idx, item in enumerate(display_items, 1):
                        # Format as key-value pairs
                        item_str = f"{idx}. " + ", ".join([f"{k}: {v}" for k, v in item.items()])
                        formatted_items.append(item_str)
                    
                    result_text = "\n".join(formatted_items)
                    result_text += f"\n\n💡 Showing first 10 of {total_count} records. Be more specific to narrow results."
                    return result_text
                else:
                    # 10 or fewer items, show all
                    formatted_items = []
                    for idx, item in enumerate(result, 1):
                        item_str = f"{idx}. " + ", ".join([f"{k}: {v}" for k, v in item.items()])
                        formatted_items.append(item_str)
                    return "\n".join(formatted_items)
            
            # Try to extract response from API response (object with nested field)
            # API might return 'query_result', 'response', 'reply', or 'answer'
            api_response = result.get('query_result', result.get('response', result.get('reply', result.get('answer', None))))
            
            if api_response:
                logger.info(f"Successfully extracted API response from field")
                # Check if the extracted response is also a list
                if isinstance(api_response, list):
                    total_count = len(api_response)
                    if total_count > 10:
                        display_items = api_response[:10]
                        formatted_items = []
                        for idx, item in enumerate(display_items, 1):
                            item_str = f"{idx}. " + ", ".join([f"{k}: {v}" for k, v in item.items()])
                            formatted_items.append(item_str)
                        result_text = "\n".join(formatted_items)
                        result_text += f"\n\n💡 Showing first 10 of {total_count} records. Be more specific to narrow results."
                        return result_text
                return api_response
            else:
                # If response structure is different, log it and return None
                logger.warning(f"Unexpected API response structure: {result}")
                return None
        else:
            logger.warning(f"{agent_type.capitalize()} agent API returned status {response.status_code}: {response.text}")
            return None
            
    except requests.exceptions.Timeout:
        logger.error(f"{agent_type.capitalize()} agent API timeout after {API_TIMEOUT}s")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"{agent_type.capitalize()} agent API error: {str(e)}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"{agent_type.capitalize()} agent JSON decode error: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"{agent_type.capitalize()} agent unexpected error: {str(e)}")
        return None

def get_finance_advice(query: str) -> str:
    """Financial Advisor - calls BI Publisher SOAP API or returns mock response"""
    logger.info(f"Finance advisor processing query: {query}")
    
    # If using mock responses, skip API call
    if USE_MOCK_RESPONSES:
        logger.info("Finance advisor using mock response (USE_MOCK_RESPONSES=True)")
        query_lower = query.lower()
        for keyword, response in MOCK_RESPONSES["finance"].items():
            if keyword in query_lower:
                logger.info(f"Finance advisor matched keyword: {keyword}")
                return response
        logger.info("Finance advisor using default response")
        return MOCK_RESPONSES["finance"]["budget"]
    
    # Call BI Publisher SOAP API
    finance_url = CONFIG.get('finance_agent_url')
    finance_username = CONFIG.get('finance_agent_username')
    finance_password = CONFIG.get('finance_agent_password')
    
    if not finance_url:
        logger.warning("Finance agent URL not configured")
        return MOCK_RESPONSES["finance"]["budget"]
    
    if not finance_username or not finance_password:
        logger.warning("Finance agent credentials not configured")
        return "Finance report API credentials not configured. Please check config.properties."
    
    try:
        # SOAP request body for BI Publisher runReport operation
        soap_body = '''<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" xmlns:pub="http://xmlns.oracle.com/oxp/service/PublicReportService">
   <soap:Header/>
   <soap:Body>
      <pub:runReport>
         <pub:reportRequest>
            <pub:attributeFormat>pdf</pub:attributeFormat>
            <pub:parameterNameValues>
               <pub:item>
                  <pub:name>P_PO_NUM</pub:name>
                  <pub:values>
                     <pub:item>55269</pub:item>
                  </pub:values>
               </pub:item>
            </pub:parameterNameValues>
            <pub:reportAbsolutePath>/Custom/ROIC/ROIC_PO_REPORTS.xdo</pub:reportAbsolutePath>
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
        logger.info(f"Using username: {finance_username}")
        logger.info(f"Password length: {len(finance_password)} chars")
        logger.debug(f"SOAP Request body: {soap_body}")
        
        # Make SOAP API call with Basic Authentication
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
        logger.debug(f"Response headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            # Parse SOAP XML response
            response_text = response.text
            logger.debug(f"SOAP Response (first 500 chars): {response_text[:500]}")
            
            # Extract reportBytes from SOAP response
            # Look for <ns2:reportBytes>...</ns2:reportBytes> or similar
            report_bytes_match = re.search(r'<[^:]+:reportBytes>([^<]+)</[^:]+:reportBytes>', response_text)
            
            if report_bytes_match:
                report_bytes = report_bytes_match.group(1).strip()
                logger.info(f"Successfully received base64 PDF from BI Publisher SOAP (length: {len(report_bytes)} chars)")
                # Return a special marker indicating PDF is available with advisor name
                return f"PDF_DOWNLOAD:Finance:{report_bytes}"
            else:
                logger.warning(f"No reportBytes found in SOAP response")
                logger.debug(f"Full SOAP response: {response_text}")
                return "Report generated but PDF data not found in SOAP response."
        elif response.status_code == 401:
            logger.error(f"Finance BI Publisher SOAP API authentication failed (401)")
            logger.error(f"Username used: {finance_username}")
            logger.error(f"Response: {response.text[:500]}")
            return "Finance report API authentication failed. Please verify username and password in config.properties."
        else:
            logger.warning(f"Finance BI Publisher SOAP API returned status {response.status_code}")
            logger.warning(f"Response text: {response.text[:500]}")
            return f"Finance report API error: HTTP {response.status_code}"
            
    except requests.exceptions.Timeout:
        logger.error(f"Finance BI Publisher SOAP API timeout after {API_TIMEOUT}s")
        return "Finance report API timeout. Please try again."
    except requests.exceptions.RequestException as e:
        logger.error(f"Finance BI Publisher SOAP API error: {str(e)}")
        return f"Finance report API error: {str(e)}"
    except Exception as e:
        logger.error(f"Finance BI Publisher SOAP unexpected error: {str(e)}")
        logger.error(f"Error details: {str(e)}", exc_info=True)
        return f"Finance report error: {str(e)}"

def get_hr_advice(query: str) -> str:
    """HR Advisor - calls API or returns mock response"""
    logger.info(f"HR advisor processing query: {query}")
    
    # Try API call first
    api_response = call_agent_api('hr', query)
    if api_response:
        return api_response
    
    # Fall back to mock responses
    query = query.lower()
    for keyword, response in MOCK_RESPONSES["hr"].items():
        if keyword in query:
            logger.info(f"HR advisor matched keyword: {keyword}")
            return response
    logger.info("HR advisor using default response")
    return MOCK_RESPONSES["hr"]["policy"]  # Default response

def get_orders_advice(query: str) -> str:
    """Orders Advisor - calls Oracle Fusion SCM Orders API or returns response"""
    logger.info(f"Orders advisor processing query: {query}")

    # If using mock responses, skip API call
    if USE_MOCK_RESPONSES:
        logger.info("Orders advisor using mock response (USE_MOCK_RESPONSES=True)")
        ql = query.lower()
        for keyword, response in MOCK_RESPONSES["orders"].items():
            if keyword in ql:
                logger.info(f"Orders advisor matched keyword: {keyword}")
                return response
        logger.info("Orders advisor using default mock response")
        return MOCK_RESPONSES["orders"]["status"]

    # Read Orders API config
    orders_url = CONFIG.get('orders_agent_url')
    orders_username = CONFIG.get('orders_agent_username')
    orders_password = CONFIG.get('orders_agent_password')

    if not orders_url:
        logger.warning("Orders agent URL not configured")
        # Fall back to mock
        ql = query.lower()
        for keyword, response in MOCK_RESPONSES["orders"].items():
            if keyword in ql:
                return response
        return MOCK_RESPONSES["orders"]["status"]

    if not orders_username or not orders_password:
        logger.warning("Orders agent credentials not configured")
        return "Orders API credentials not configured. Please check config.properties."

    # Determine if user asked about a specific order key/id
    order_key = None
    try:
        # First, look for SourceOrderSystem:SourceTransactionId format (e.g., OPS:300000203741093)
        m = re.search(r"\b[A-Z]{2,10}:\d{9,}\b", query)
        if m:
            order_key = m.group(0)
        else:
            # Otherwise, look for a long numeric HeaderId anywhere in the prompt
            m2 = re.search(r"\b\d{9,15}\b", query)
            if m2:
                order_key = m2.group(0)
    except Exception as e:
        logger.debug(f"Order key parsing error: {str(e)}")

    headers = {
        "Accept": "application/json"
    }
    auth = HTTPBasicAuth(orders_username, orders_password)

    try:
        if order_key:
            # Fetch specific order
            url = f"{orders_url}/{order_key}"
            logger.info(f"Calling Orders API (detail) at {url}")
            resp = requests.get(url, headers=headers, auth=auth, timeout=API_TIMEOUT, verify=True)
            logger.info(f"Orders detail response status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                # Build concise summary
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
                    f"Order {ok}\n"
                    f"Status: {status}\n"
                    f"Submitted By: {submitted_by} on {submitted_date}\n\n"
                    f"Top Lines:\n{lines_text}"
                )
            elif resp.status_code == 404:
                return f"No sales order found for key/id '{order_key}'."
            elif resp.status_code == 401:
                logger.error("Orders API authentication failed (401)")
                return "Orders API authentication failed. Please verify username/password in config.properties."
            else:
                logger.warning(f"Orders detail API returned {resp.status_code}: {resp.text[:300]}")
                return f"Orders API error: HTTP {resp.status_code}"
        else:
            # Fetch list of sales orders with explicit default limit and client-side sort by latest date
            params = {"limit": 10}
            logger.info(f"Calling Orders API (list, limit=10) at {orders_url}")
            resp = requests.get(orders_url, params=params, headers=headers, auth=auth, timeout=API_TIMEOUT, verify=True)
            logger.info(f"Orders list response status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                items = data.get('items') or []
                if not items:
                    return "No recent sales orders were returned by the API."
                # Sort by LastUpdateDate descending (latest first)
                def _parse_dt(s):
                    try:
                        # Handle ISO 8601 with possible trailing Z
                        return datetime.fromisoformat(s.replace('Z', '+00:00')) if isinstance(s, str) else datetime.min
                    except Exception:
                        return datetime.min
                items_sorted = sorted(items, key=lambda it: _parse_dt(it.get('LastUpdateDate')), reverse=True)
                
                # Limit to first 10 for display
                display_items = items_sorted[:10]
                total_count = len(items_sorted)
                has_more = total_count > 10
                
                lines = []
                for it in display_items:
                    ok = it.get('OrderKey', 'N/A')
                    status = it.get('StatusCode', 'N/A')
                    created_by = it.get('CreatedBy', 'N/A')
                    last_upd = it.get('LastUpdateDate', 'N/A')
                    lines.append(f"• {ok} | Status: {status} | By: {created_by} | Updated: {last_upd}")
                
                result_text = f"Recent Sales Orders (showing 10 of {total_count}):\n" + "\n".join(lines)
                
                if has_more:
                    result_text += f"\n\n💡 Showing first 10 of {total_count} orders. Use specific Order ID for details."
                
                return result_text
            elif resp.status_code == 401:
                logger.error("Orders API authentication failed (401)")
                return "Orders API authentication failed. Please verify username/password in config.properties."
            else:
                logger.warning(f"Orders list API returned {resp.status_code}: {resp.text[:300]}")
                return f"Orders API error: HTTP {resp.status_code}"
    except requests.exceptions.Timeout:
        logger.error(f"Orders API timeout after {API_TIMEOUT}s")
        return "Orders API timeout. Please try again."
    except requests.exceptions.RequestException as e:
        logger.error(f"Orders API error: {str(e)}")
        return f"Orders API error: {str(e)}"
    except json.JSONDecodeError as e:
        logger.error(f"Orders API JSON decode error: {str(e)}")
        return "Orders API returned invalid response."
    except Exception as e:
        logger.error(f"Orders advisor unexpected error: {str(e)}")
        return f"Orders API error: {str(e)}"

def get_general_advice(query: str) -> str:
    """General Agent - handles both database queries (via ORDS NL2SQL) and general knowledge (via OCI Gen AI)"""
    logger.info(f"General agent processing query: {query}")
    
    # Detect if this is a database/data query (NL2SQL scenario)
    database_keywords = [
        'list', 'show', 'get', 'find', 'search', 'query', 'select', 'count', 'sum', 'average',
        'table', 'database', 'record', 'data', 'customer', 'employee', 'product', 'item',
        'all', 'total', 'how many', 'sql', 'translate'
    ]
    
    query_lower = query.lower()
    is_database_query = any(keyword in query_lower for keyword in database_keywords)
    
    # Try ORDS GenAI Module first for database/NL2SQL queries
    if is_database_query:
        logger.info("Detected database query, attempting ORDS GenAI Module (NL2SQL)")
        api_response = call_agent_api('general', query)
        if api_response:
            logger.info("ORDS GenAI Module successfully handled database query")
            return api_response
        else:
            logger.info("ORDS GenAI Module not available or failed, trying OCI Gen AI as fallback")
    
    # Use OCI Gen AI Inference API for general knowledge questions or as fallback
    if genai_client:
        try:
            if is_database_query:
                logger.info("Using OCI Gen AI as fallback for database query")
            else:
                logger.info("Using OCI Gen AI Inference API for general knowledge question")
            
            # Create chat request with the user's query
            chat_request = CohereChatRequest(
                message=query,
                max_tokens=500,
                temperature=0.7,
                frequency_penalty=0,
                top_p=0.75,
                top_k=0
            )
            
            chat_details = ChatDetails(
                serving_mode=OnDemandServingMode(
                    model_id=GENAI_MODEL_ID
                ),
                compartment_id=os.getenv('OCI_TENANCY'),
                chat_request=chat_request
            )
            
            logger.info(f"Calling OCI Gen AI with model: {GENAI_MODEL_ID}")
            response = genai_client.chat(chat_details)
            
            # Extract the response
            if response.data and response.data.chat_response:
                answer = response.data.chat_response.text.strip()
                logger.info(f"OCI Gen AI response received (length: {len(answer)} chars)")
                return answer
            else:
                logger.warning("No response from OCI Gen AI")
                return "I apologize, but I couldn't generate a response at this time. Please try again."
                
        except Exception as e:
            logger.error(f"Error calling OCI Gen AI: {e}")
            return f"I encountered an error while processing your question: {str(e)}"
    else:
        # Fallback if Gen AI client not available
        logger.warning("OCI Gen AI client not available, using fallback response")
        for keyword, response in MOCK_RESPONSES["general"].items():
            if keyword in query_lower:
                logger.info(f"General agent matched keyword: {keyword}")
                return response
        
        # Default general response
        logger.info("General agent using default response")
        return MOCK_RESPONSES["general"]["help"]

def get_reports_advice(query: str) -> str:
    """Reports Advisor - calls Oracle Analytics Cloud Workbook Export API or returns mock response"""
    logger.info(f"Reports advisor processing query: {query}")

    if USE_MOCK_RESPONSES:
        logger.info("Reports advisor using mock response (USE_MOCK_RESPONSES=True)")
        ql = query.lower()
        for keyword, response in MOCK_RESPONSES["reports"].items():
            if keyword in ql:
                logger.info(f"Reports advisor matched keyword: {keyword}")
                return response
        return MOCK_RESPONSES["reports"]["analytics"]

    reports_url = CONFIG.get('reports_agent_url')
    reports_username = CONFIG.get('reports_agent_username')
    reports_password = CONFIG.get('reports_agent_password')

    if not reports_url:
        logger.warning("Reports agent URL not configured")
        ql = query.lower()
        for keyword, response in MOCK_RESPONSES["reports"].items():
            if keyword in ql:
                return response
        return MOCK_RESPONSES["reports"]["analytics"]

    if not reports_username or not reports_password:
        logger.warning("Reports agent credentials not configured")
        return "Reports API credentials not configured. Please check config.properties."

    try:
        api_version = "20210901"
        workbook_id = CONFIG.get('reports_workbook_id', "L3NoYXJlZC9SQ09FL0Fic2VuY2UgV29ya2Jvb2s")
        export_format = "pdf"

        export_url = f"{reports_url}/api/{api_version}/catalog/workbooks/{workbook_id}/exports"
        payload = {
            "name": "Absence Workbook Report",
            "type": "file",
            "canvasIds": ["snapshot!canvas!1"],
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

# HTML Template for multi-agent advisory system
template = r"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>Chat - Advisors</title>
    <style>
      body { font-family: Arial, sans-serif; background:#f6f8fb; margin:0; padding:20px }
      .container { max-width:760px; margin:0 auto; background:#fff; border-radius:8px; box-shadow:0 4px 12px rgba(0,0,0,0.06); overflow:hidden }
      .header { background:#0b5ed7; color:#fff; padding:12px 16px }
      .messages { height:420px; overflow:auto; padding:12px; border-bottom:1px solid #eee }
      .msg { margin:8px 0; padding:10px 12px; border-radius:6px; max-width:80%; white-space: pre-wrap; }
      .msg.user { background:#0b5ed7; color:#fff; margin-left:auto }
      .msg.agent { background:#f1f5f9; color:#111; margin-right:auto }
      .input-area { display:flex; gap:8px; padding:12px }
      .input-area input { flex:1; padding:10px; border-radius:6px; border:1px solid #ddd }
      .input-area button { padding:10px 14px; background:#0b5ed7; color:#fff; border:none; border-radius:6px }
      .hint { font-size:12px; color:#666; padding:8px 12px }
    </style>
  </head>
  <body>
    <div class="container">
        <div class="header">RCOE Enterprise Advisors</div>
            <div style="padding:12px; background:#eef6ff; color:#064e8a;">
                <strong>Hi there, how may I assist you today !!</strong><br><br>
                Ask our advisors anything about Your Data, Finance, HR, Sales, Analytic Reports  or get general help. <br> Choose a sample question to start quickly.
            </div>
                    <div style="padding:10px 12px; display:flex; gap:8px; flex-wrap:wrap; background:#fafafa;">
                        <button onclick="selectSample('GENERAL: Translate to SQL: list all customers details ?')" style="padding:6px 10px;border-radius:6px;border:1px solid #ddd; background:#fff; cursor:pointer">🤖 Talk With Data </button>
                        <button onclick="selectSample('Show me Finance Reports ?')" style="padding:6px 10px;border-radius:6px;border:1px solid #ddd; background:#fff; cursor:pointer">📈 Finance Reports</button>
                        <button onclick="selectSample('List out all employee details ?')" style="padding:6px 10px;border-radius:6px;border:1px solid #ddd; background:#fff; cursor:pointer">👥 Employee Reports </button>
                        <button onclick="selectSample('Show me sales Order reports ?')" style="padding:6px 10px;border-radius:6px;border:1px solid #ddd; background:#fff; cursor:pointer">📦 Sales Reports</button>
                        <button onclick="selectSample('Show me Fusion Analytics Dashboards ?')" style="padding:6px 10px;border-radius:6px;border:1px solid #ddd; background:#fff; cursor:pointer">📊 Analytic Reports</button>
                        <button onclick="clearChat()" style="padding:6px 10px;border-radius:6px;border:1px solid #ddd; background:#fff; cursor:pointer; margin-left:auto;">🧹 Clear Chat</button>
                    </div>
            <div id="messages" class="messages"></div>
      <div class="input-area">
        <input id="input" placeholder="Ask about Finance, HR, Sales Orders, Analytic Reports or General Queries about your data ..." />
        <button id="send">Send</button>
      </div>
      <div class="hint">Try: "What's our Finance Reports say ?" Or "Show me about all employee details"</div>
      <div class="hint">🚀 Intelligent routing via OCI Gen AI </div>
    </div>

    <script>
      const messagesEl = document.getElementById('messages');
      const inputEl = document.getElementById('input');
      const sendBtn = document.getElementById('send');

      function addMessage(text, cls='agent'){
        const el = document.createElement('div');
        el.className = 'msg ' + (cls === 'user' ? 'user' : 'agent');
        // Replace ** with blank lines for better spacing
        text = text.replace(/\*\*/g, '');
        el.textContent = text;
        messagesEl.appendChild(el);
        messagesEl.scrollTop = messagesEl.scrollHeight;
      }

                    function selectSample(text, auto=false){
                        // Populate the input with the sample question. By default do not auto-send.
                        inputEl.value = text;
                        inputEl.focus();
                        if(auto) send();
                    }

                    function clearChat(){
                        messagesEl.innerHTML = '';
                    }

            async function send(){
        const prompt = inputEl.value.trim();
        if(!prompt) return;
        addMessage(prompt, 'user');
        inputEl.value = '';
        addMessage('Thinking...', 'agent');

        try{
          const res = await fetch('/chat', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({prompt}) });
          const data = await res.json();
          // remove the last 'Thinking...' element
          const last = messagesEl.querySelectorAll('.msg.agent');
          if(last.length) last[last.length-1].remove();
          
          // Check if response has PDF download
          if(data.has_pdf && data.download_url){
            const msgDiv = document.createElement('div');
            msgDiv.className = 'msg agent';
            msgDiv.innerHTML = data.reply + '<br><br><button onclick="downloadPDF()" style="background:#0b5ed7;color:#fff;border:none;padding:10px 20px;border-radius:6px;cursor:pointer;font-size:14px;">📥 Download PDF Report</button>';
            messagesEl.appendChild(msgDiv);
            messagesEl.scrollTop = messagesEl.scrollHeight;
            window.pdfDownloadUrl = data.download_url;
          }else{
            addMessage(data.reply || 'No response from server', 'agent');
          }
        }catch(e){
          const last = messagesEl.querySelectorAll('.msg.agent');
          if(last.length) last[last.length-1].remove();
          addMessage('Error contacting server', 'agent');
        }
      }

      function downloadPDF(){
        if(window.pdfDownloadUrl){
          window.open(window.pdfDownloadUrl, '_blank');
        }
      }

    sendBtn.addEventListener('click', send);
      inputEl.addEventListener('keydown', (e)=>{ if(e.key === 'Enter') send(); });
    </script>
  </body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(template)



def format_response(result: Dict) -> str:
    """Format the advisor responses with visual structure"""
    logger.debug("Formatting response")
    
    # Check if response contains download markers - return as-is without formatting
    for advisor, response in result['advisors']:
        if "PDF_DOWNLOAD:" in response or "REPORT_DOWNLOAD:" in response:
            logger.debug("Download marker detected, returning unformatted response")
            return response
    
    if len(result['advisors']) > 1:
        formatted_result = "🎯 Multiple advisors have insights to share:\n\n"
    else:
        formatted_result = "🎯 Here's what I found: "
    
    for advisor, response in result['advisors']:
        formatted_result += f"{advisor}\n"  # Advisor title
        formatted_result += "─" * 28 + "\n"  # Separator with extra newline
        formatted_result += f"{response}\n"  # Response with extra spacing
        
    if len(result['advisors']) == 1:
        advisor_type = result['advisors'][0][0].split()[0].lower()
        if advisor_type == 'general':
            formatted_result += "\n💡 I can route your questions to Finance, HR, Orders, or Reports advisors."
        elif advisor_type == 'finance':
            formatted_result += "\n💡 You can also ask about budgets, expenses, or revenue forecasts."
        elif advisor_type == 'hr':
            formatted_result += "\n💡 Feel free to ask about benefits, leaves, or company policies."
        elif advisor_type == 'orders':
            formatted_result += "\n💡 You can inquire about inventory levels or return rates as well."
        elif advisor_type == 'reports':
            formatted_result += "\n💡 You can request analytics dashboards or workbook exports."
    
    formatted_result += f"\n\n⏰ {datetime.now().strftime('%H:%M:%S')}"
    logger.debug("Response formatting completed")
    return formatted_result

def detect_intent_with_genai(prompt: str) -> str:
    """
    Use OCI Gen AI to detect user intent and determine which advisor to route to.
    Returns: 'general', 'finance', 'hr', 'orders', 'reports', or None if detection fails
    """
    if not genai_client:
        logger.warning("OCI Gen AI client not available, skipping intent detection")
        return None
    
    try:
        # Create a prompt for intent classification
        system_prompt = """You are an intent classification assistant for a multi-agent advisory system.
Based on the user's question, determine which advisor should handle it.

Available advisors:
- general: General inquiries, help, capabilities, services overview
- finance: Revenue, budget, expenses, costs, financial reports, profit/loss
- hr: HR policies, benefits, leave, employee matters, work policies, holidays
- orders: Sales orders, inventory, delivery, returns, shipping, stock, products
- reports: Analytics, workbooks, dashboards, OAC exports, visualizations

Respond with ONLY ONE WORD - the advisor name (general, finance, hr, orders, or reports).
If the query could match multiple advisors, choose the most relevant one.

User question: {prompt}

Answer (one word only):"""

        classification_prompt = system_prompt.format(prompt=prompt)
        
        # Create chat request using Cohere Command model
        chat_request = CohereChatRequest(
            message=classification_prompt,
            max_tokens=10,
            temperature=0.1,  # Low temperature for consistent classification
            frequency_penalty=0,
            top_p=0.75,
            top_k=0
        )
        
        chat_details = ChatDetails(
            serving_mode=OnDemandServingMode(
                model_id=GENAI_MODEL_ID
            ),
            compartment_id=os.getenv('OCI_TENANCY'),
            chat_request=chat_request
        )
        
        logger.info(f"Calling OCI Gen AI for intent detection with model: {GENAI_MODEL_ID}")
        response = genai_client.chat(chat_details)
        
        # Extract the intent from response
        if response.data and response.data.chat_response:
            intent = response.data.chat_response.text.strip().lower()
            logger.info(f"OCI Gen AI detected intent: {intent}")
            
            # Validate the intent
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

def process_user_query(prompt: str) -> Dict:
    """Process user query and route to appropriate advisor"""
    logger.info(f"Processing new query: {prompt}")
    prompt_lower = prompt.lower()
    
    # Step 1: Try OCI Gen AI intent detection first
    detected_intent = None
    logger.info(f"Gen AI client available: {bool(genai_client)} | intent mode: {GENAI_INTENT_MODE}")
    if genai_client and GENAI_INTENT_MODE != 'off':
        logger.info("Attempting OCI Gen AI intent detection...")
        detected_intent = detect_intent_with_genai(prompt)
        logger.info(f"Gen AI detection result: {detected_intent}")
        
        if detected_intent:
            logger.info(f"✓ OCI Gen AI routed to: {detected_intent}")
            responses = []
            
            # Route based on Gen AI detected intent
            if detected_intent == 'general':
                response = get_general_advice(prompt)
                responses.append(("General Agent 🤖", response))
            elif detected_intent == 'finance':
                response = get_finance_advice(prompt)
                responses.append(("Finance Advisor 💰", response))
            elif detected_intent == 'hr':
                response = get_hr_advice(prompt)
                responses.append(("HR Advisor 👥", response))
            elif detected_intent == 'orders':
                response = get_orders_advice(prompt)
                responses.append(("Orders Advisor 📦", response))
            elif detected_intent == 'reports':
                response = get_reports_advice(prompt)
                responses.append(("Reports Advisor 📊", response))
            
            return {"advisors": responses}
        elif GENAI_INTENT_MODE == 'force':
            logger.warning("Gen AI did not return an intent but mode is 'force'; continuing with keyword fallback.")
    else:
        logger.info("Skipping Gen AI intent detection (disabled or client unavailable)")
    
    # Step 2: Fallback to keyword-based routing if Gen AI fails or not available
    logger.info("Using keyword-based routing (Gen AI not available or failed)")
    
    # Keyword maps for each advisor
    advisor_keywords = {
        'general': ['general', 'help', 'what can you do', 'capabilities', 'services', 'assist', 'how can', 'what do you', 'tell me about', 'who are you', 'what services','nlp','nlp2sql'],
        'finance': ['finance', 'revenue', 'budget', 'expense', 'cost', 'money', 'financial', 'profit', 'loss'],
        'hr': ['hr', 'policy', 'benefit', 'leave', 'employee', 'work', 'holiday', 'vacation', 'staff'],
        'orders': ['order', 'inventory', 'delivery', 'return', 'shipping', 'stock', 'product', 'item','sales'],
        'reports': ['workbook', 'analytics', 'export', 'oac', 'dashboard', 'visualization']
    }
    
    logger.debug(f"Starting keyword analysis for query: {prompt_lower}")
    responses = []
    
    # Check for general queries first (including explicit "general" keyword)
    if any(keyword in prompt_lower for keyword in advisor_keywords['general']):
        logger.info("General keyword detected, routing to General Agent")
        response = get_general_advice(prompt)
        responses.append(("General Agent 🤖", response))
        return {"advisors": responses}  # Return immediately for general queries
    
    # Check each specific advisor's keywords
    if any(keyword in prompt_lower for keyword in advisor_keywords['finance']):
        response = get_finance_advice(prompt)
        responses.append(("Finance Advisor 💰", response))
        
    if any(keyword in prompt_lower for keyword in advisor_keywords['hr']):
        response = get_hr_advice(prompt)
        responses.append(("HR Advisor 👥", response))
        
    if any(keyword in prompt_lower for keyword in advisor_keywords['orders']):
        response = get_orders_advice(prompt)
        responses.append(("Orders Advisor 📦", response))
        
    if any(keyword in prompt_lower for keyword in advisor_keywords['reports']):
        response = get_reports_advice(prompt)
        responses.append(("Reports Advisor 📊", response))
            
    # If no specific advisor was matched, try to infer from context or use general agent
    if not responses:
        # Try to infer the most relevant advisor
        word_counts = {
            'finance': sum(prompt_lower.count(word) for word in advisor_keywords['finance']),
            'hr': sum(prompt_lower.count(word) for word in advisor_keywords['hr']),
            'orders': sum(prompt_lower.count(word) for word in advisor_keywords['orders']),
            'reports': sum(prompt_lower.count(word) for word in advisor_keywords['reports'])
        }
        
        max_count = max(word_counts.values())
        if max_count > 0:
            # Use the most relevant advisor
            advisor = max(word_counts.items(), key=lambda x: x[1])[0]
            if advisor == 'finance':
                responses.append(("Finance Advisor 💰", get_finance_advice(prompt)))
            elif advisor == 'hr':
                responses.append(("HR Advisor 👥", get_hr_advice(prompt)))
            elif advisor == 'orders':
                responses.append(("Orders Advisor 📦", get_orders_advice(prompt)))
            else:
                responses.append(("Reports Advisor 📊", get_reports_advice(prompt)))
        else:
            # Use General Agent for truly general or unclear queries
            logger.info("No specific advisor matched, using General Agent")
            response = get_general_advice(prompt)
            responses = [("General Agent 🤖", response)]
    
    return {"advisors": responses}

@app.route('/chat', methods=['POST'])
def chat():
    logger.info("Received chat request")
    try:
        data = request.get_json()
        if not data:
            logger.warning("Invalid request: No JSON data received")
            return jsonify({"reply": "⚠️ Error: Invalid request format"}), 400
            
        prompt = data.get('prompt', '')
        logger.info(f"Received prompt: {prompt}")
        
        if not prompt or not isinstance(prompt, str):
            logger.warning(f"Invalid prompt received: {type(prompt)}")
            return jsonify({"reply": "⚠️ Error: Please provide a valid question"}), 400
        
        # Process the query through our advisor system
        logger.info("Processing query through advisor system")
        result = process_user_query(prompt.strip())
        
        # Check if response contains PDF download or Report download
        formatted_response = format_response(result)
        if "PDF_DOWNLOAD:" in formatted_response:
            # Extract advisor name and base64 PDF data
            # Format: PDF_DOWNLOAD:AdvisorName:base64data
            parts = formatted_response.split("PDF_DOWNLOAD:")[1].strip().split(":", 1)
            if len(parts) == 2:
                advisor_name = parts[0]
                pdf_data = parts[1]
            else:
                # Fallback if old format
                advisor_name = "Finance"
                pdf_data = formatted_response.split("PDF_DOWNLOAD:")[1].strip()
            
            # Generate unique download ID and store in server-side storage
            download_id = str(uuid.uuid4())
            download_storage[download_id] = {
                'type': 'pdf',
                'data': pdf_data,
                'advisor': advisor_name,
                'timestamp': datetime.now().strftime('%Y%m%d_%H%M%S')
            }
            logger.info(f"PDF data stored in server storage with ID: {download_id}")
            
            # Return response with download link - show advisor name clearly
            response_text = f"🎯 Here's what I found: {advisor_name} Advisor 💰\n────────────────────────────\n📄 Your report is ready!\n\nClick the button below to download the PDF report."
            return jsonify({
                "reply": response_text,
                "has_pdf": True,
                "download_url": f"/download_pdf/{download_id}"
            })
        elif "REPORT_DOWNLOAD:" in formatted_response:
            # Extract advisor name, format and base64 data
            # Format: REPORT_DOWNLOAD:AdvisorName:FORMAT:base64data
            download_marker = formatted_response.split("REPORT_DOWNLOAD:")[1].strip()
            parts = download_marker.split(":", 2)
            if len(parts) == 3:
                advisor_name = parts[0]
                report_format = parts[1].lower()
                report_data = parts[2]
                # Generate unique download ID and store in server-side storage
                download_id = str(uuid.uuid4())
                download_storage[download_id] = {
                    'type': 'report',
                    'format': report_format,
                    'data': report_data,
                    'advisor': advisor_name,
                    'timestamp': datetime.now().strftime('%Y%m%d_%H%M%S')
                }
                logger.info(f"Report data ({report_format}) stored in server storage with ID: {download_id}")
                
                # Return response with download link - show advisor name clearly
                response_text = f"🎯 Here's what I found:\n\n{advisor_name} Advisor 📊\n────────────────────────────\n📊 Your analytics report is ready!\n\nClick the button below to download the {report_format.upper()} report."
                return jsonify({
                    "reply": response_text,
                    "has_pdf": True,  # Reuse the same flag for UI compatibility
                    "download_url": f"/download_report/{download_id}"
                })
            else:
                logger.error("Invalid REPORT_DOWNLOAD format")
                return jsonify({
                    "reply": "⚠️ Error: Invalid report format"
                }), 500
        
        # Log the response
        logger.info(f"Generated response with {len(result['advisors'])} advisor(s)")
        return jsonify({"reply": formatted_response})
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}", exc_info=True)
        return jsonify({"reply": "⚠️ An error occurred while processing your request."}), 500

@app.route('/download_pdf/<download_id>', methods=['GET'])
def download_pdf(download_id):
    """Download the PDF report from server storage"""
    try:
        download_data = download_storage.get(download_id)
        if not download_data or download_data.get('type') != 'pdf':
            logger.warning(f"No PDF data found for download ID: {download_id}")
            return "No PDF available for download", 404
        
        # Decode base64 PDF
        pdf_bytes = base64.b64decode(download_data['data'])
        
        # Create filename with timestamp
        timestamp = download_data.get('timestamp', datetime.now().strftime('%Y%m%d_%H%M%S'))
        filename = f"Finance_Report_{timestamp}.pdf"
        
        logger.info(f"Sending PDF download: {filename}")
        
        # Note: Keeping data in storage to allow retries/refreshes
        # Could implement cleanup based on timestamp later if needed
        
        # Send file as download
        return send_file(
            BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        logger.error(f"Error downloading PDF: {str(e)}", exc_info=True)
        return "Error downloading PDF", 500

@app.route('/download_report/<download_id>', methods=['GET'])
def download_report(download_id):
    """Download the analytics report from server storage"""
    try:
        download_data = download_storage.get(download_id)
        if not download_data or download_data.get('type') != 'report':
            logger.warning(f"No report data found for download ID: {download_id}")
            return "No report available for download", 404
        
        report_format = download_data.get('format', 'pdf')
        
        # Decode base64 report
        report_bytes = base64.b64decode(download_data['data'])
        
        # Determine MIME type and extension based on format
        format_mapping = {
            'pdf': ('application/pdf', 'pdf'),
            'png': ('image/png', 'png'),
            'xlsx': ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'xlsx'),
            'csv': ('text/csv', 'csv')
        }
        
        mimetype, extension = format_mapping.get(report_format, ('application/octet-stream', 'bin'))
        
        # Create filename with timestamp
        timestamp = download_data.get('timestamp', datetime.now().strftime('%Y%m%d_%H%M%S'))
        filename = f"Analytics_Report_{timestamp}.{extension}"
        
        logger.info(f"Sending report download: {filename}")
        
        # Note: Keeping data in storage to allow retries/refreshes
        # Could implement cleanup based on timestamp later if needed
        
        # Send file as download
        return send_file(
            BytesIO(report_bytes),
            mimetype=mimetype,
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        logger.error(f"Error downloading report: {str(e)}", exc_info=True)
        return "Error downloading report", 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
