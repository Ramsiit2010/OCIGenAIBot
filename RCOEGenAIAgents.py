"""
RCOE Gen AI Advisor Systems - MCP Server Architecture
Uses OCI Generative AI for intent detection and routes to registered MCP servers
No keyword-based fallback - pure intent-driven routing
"""
from flask import Flask, render_template_string, request, jsonify, send_file
import os
import logging
import json
from datetime import datetime
from typing import Dict, Optional
import base64
from io import BytesIO
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

# MCP Server imports
from mcp_servers.advisors import (
    GeneralMCPServer,
    FinanceMCPServer,
    HRMCPServer,
    OrdersMCPServer,
    ReportsMCPServer
)

# Configure logging
logging.basicConfig(
    filename='rcoe_genai_agents.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Server-side storage for downloads
download_storage = {}

logger.info("RCOE Gen AI Agents Application initialized")


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
            return json.load(f)
    except Exception as e:
        logger.warning(f"Could not load {spec_file}: {e}")
        return None


# Load configuration
CONFIG = load_config()
API_TIMEOUT = int(CONFIG.get('api_timeout', '30'))

# Load API specs
API_SPEC_GENERAL = load_api_spec('api_spec_general.json')
API_SPEC_FINANCE = load_api_spec('api_spec_finance.json')
API_SPEC_HR = load_api_spec('api_spec_hr.json')
API_SPEC_ORDERS = load_api_spec('api_spec_orders.json')
API_SPEC_REPORTS = load_api_spec('api_spec_reports.json')

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
        
        if oci_user and oci_key_file and oci_fingerprint and oci_tenancy:
            # Resolve key file path - support both absolute and relative paths
            if os.path.isabs(oci_key_file):
                key_file_path = oci_key_file
            elif oci_key_file.startswith('~'):
                key_file_path = os.path.expanduser(oci_key_file)
            else:
                # Relative path - resolve from project directory
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
            logger.info(f"✓ OCI Gen AI client initialized for {genai_region}")
        else:
            logger.warning("OCI credentials not found in .env - intent detection disabled")
    except Exception as e:
        logger.error(f"Failed to initialize OCI Gen AI client: {e}")
        genai_client = None
else:
    logger.warning("OCI SDK not available - intent detection disabled")

# Gen AI model configuration
GENAI_MODEL_ID = 'cohere.command-plus-latest'
logger.info(f"Gen AI model: {GENAI_MODEL_ID}")

# Initialize and register MCP servers
mcp_servers = {}

logger.info("Initializing MCP servers...")

# General MCP Server
general_server = GeneralMCPServer(CONFIG, API_SPEC_GENERAL)
if general_server.register():
    mcp_servers['general'] = general_server

# Finance MCP Server
finance_server = FinanceMCPServer(CONFIG, API_SPEC_FINANCE)
if finance_server.register():
    mcp_servers['finance'] = finance_server

# HR MCP Server
hr_server = HRMCPServer(CONFIG, API_SPEC_HR)
if hr_server.register():
    mcp_servers['hr'] = hr_server

# Orders MCP Server
orders_server = OrdersMCPServer(CONFIG, API_SPEC_ORDERS)
if orders_server.register():
    mcp_servers['orders'] = orders_server

# Reports MCP Server
reports_server = ReportsMCPServer(CONFIG, API_SPEC_REPORTS)
if reports_server.register():
    mcp_servers['reports'] = reports_server

logger.info(f"✓ {len(mcp_servers)} MCP servers registered: {list(mcp_servers.keys())}")


def detect_intent_with_genai(prompt: str) -> Optional[str]:
    """
    Use OCI Gen AI to detect user intent
    
    Args:
        prompt: User query
        
    Returns:
        str: Detected advisor name (general/finance/hr/orders/reports) or None
    """
    if not genai_client:
        logger.warning("Gen AI client not available for intent detection")
        return None
    
    try:
        classification_prompt = f"""You are an intent classification assistant for an enterprise advisory system.
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
        
        chat_request = CohereChatRequest(
            message=classification_prompt,
            max_tokens=10,
            temperature=0.1,
            frequency_penalty=0,
            top_p=0.75,
            top_k=0
        )
        
        chat_details = ChatDetails(
            serving_mode=OnDemandServingMode(model_id=GENAI_MODEL_ID),
            compartment_id=os.getenv('OCI_TENANCY'),
            chat_request=chat_request
        )
        
        logger.info(f"[Intent Detection] Calling Gen AI with model: {GENAI_MODEL_ID}")
        response = genai_client.chat(chat_details)
        
        # Extract intent
        if response.data and response.data.chat_response:
            intent = response.data.chat_response.text.strip().lower()
            logger.info(f"✓ Gen AI detected intent: '{intent}'")
            
            # Validate
            valid_intents = ['general', 'finance', 'hr', 'orders', 'reports']
            if intent in valid_intents:
                return intent
            else:
                logger.warning(f"Invalid intent from Gen AI: '{intent}'")
                return None
        else:
            logger.warning("No response from Gen AI")
            return None
            
    except Exception as e:
        logger.error(f"Error in Gen AI intent detection: {e}")
        return None


def route_to_mcp_server(prompt: str) -> Dict:
    """
    Route user query to appropriate MCP server using Gen AI intent detection
    
    Args:
        prompt: User query
        
    Returns:
        dict: Response with advisor and message
    """
    logger.info(f"[Routing] Processing query: {prompt}")
    
    # Detect intent with Gen AI
    detected_intent = detect_intent_with_genai(prompt)
    
    if not detected_intent:
        logger.warning("[Routing] Gen AI intent detection failed or unavailable")
        # Fallback to general advisor when intent detection fails
        detected_intent = 'general'
        logger.info("[Routing] Defaulting to General advisor")
    
    # Route to appropriate MCP server
    if detected_intent in mcp_servers:
        server = mcp_servers[detected_intent]
        logger.info(f"[Routing] Routing to MCP server: {server.name}")
        
        response = server.handle_request(prompt)
        
        # Format advisor label
        advisor_labels = {
            'general': 'General Agent 🤖',
            'finance': 'Finance Advisor 💰',
            'hr': 'HR Advisor 👥',
            'orders': 'Orders Advisor 📦',
            'reports': 'Reports Advisor 📊'
        }
        
        return {
            "advisor": advisor_labels.get(detected_intent, detected_intent.capitalize()),
            "response": response,
            "intent": detected_intent
        }
    else:
        logger.error(f"[Routing] No MCP server registered for intent: {detected_intent}")
        return {
            "advisor": "System",
            "response": f"No advisor available for '{detected_intent}' queries.",
            "intent": None
        }


# HTML Template
template = r"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>RCOE Gen AI Advisor Systems</title>
    <style>
      body { font-family: Arial, sans-serif; background:#f6f8fb; margin:0; padding:20px }
      .container { max-width:760px; margin:0 auto; background:#fff; border-radius:8px; box-shadow:0 4px 12px rgba(0,0,0,0.06); overflow:hidden }
      .header { background:#0b5ed7; color:#fff; padding:12px 16px }
      .subheader { padding:12px; background:#eef6ff; color:#064e8a; }
      .messages { height:420px; overflow:auto; padding:12px; border-bottom:1px solid #eee }
      .msg { margin:8px 0; padding:10px 12px; border-radius:6px; max-width:80%; white-space: pre-wrap; }
      .msg.user { background:#0b5ed7; color:#fff; margin-left:auto }
      .msg.agent { background:#f1f5f9; color:#111; margin-right:auto }
      .input-area { display:flex; gap:8px; padding:12px }
      .input-area input { flex:1; padding:10px; border-radius:6px; border:1px solid #ddd }
      .input-area button { padding:10px 14px; background:#0b5ed7; color:#fff; border:none; border-radius:6px; cursor:pointer }
      .hint { font-size:12px; color:#666; padding:8px 12px }
      .samples { padding:10px 12px; display:flex; gap:8px; flex-wrap:wrap; background:#fafafa; }
      .samples button { padding:6px 10px; border-radius:6px; border:1px solid #ddd; background:#fff; cursor:pointer }
    </style>
  </head>
  <body>
    <div class="container">
      <div class="header">RCOE Gen AI Advisor Systems</div>
      <div style="padding:12px; background:#eef6ff; color:#064e8a;">
                <strong>Hi there, how may I assist you today !!</strong><br><br>
                Ask our advisors anything about Finance, HR, Sales, Analytic Reports  or get general help. <br> Choose a sample question to start quickly.
      </div>
      <div class="samples">
        <button onclick="selectSample('Show general data for Customers and their cards ?')">🤖 General Help</button>
        <button onclick="selectSample('Show me Finance Reports ?')">📈 Finance</button>
        <button onclick="selectSample('List employee details ?')">👥 HR</button>
        <button onclick="selectSample('Show sales orders ?')">📦 Orders</button>
        <button onclick="selectSample('Show Analytics Dashboards ?')">📊 Reports</button>
        <button onclick="clearChat()" style="margin-left:auto;">🧹 Clear</button>
      </div>
      <div id="messages" class="messages"></div>
      <div class="input-area">
        <input id="input" placeholder="Ask about Finance, HR, Sales Orders, Analytic Reports or General Queries about your data ..." />
        <button id="send">Send</button>
      </div>
      <div class="hint">🚀 Intelligent routing via OCI Gen AI • MCP Server architecture</div>
    </div>

    <script>
      const messagesEl = document.getElementById('messages');
      const inputEl = document.getElementById('input');
      const sendBtn = document.getElementById('send');

      function addMessage(text, cls='agent'){
        const el = document.createElement('div');
        el.className = 'msg ' + (cls === 'user' ? 'user' : 'agent');
        el.textContent = text.replace(/\*\*/g, '');
        messagesEl.appendChild(el);
        messagesEl.scrollTop = messagesEl.scrollHeight;
      }

      function selectSample(text){
        inputEl.value = text;
        inputEl.focus();
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
          const res = await fetch('/chat', { 
            method:'POST', 
            headers:{'Content-Type':'application/json'}, 
            body: JSON.stringify({prompt}) 
          });
          const data = await res.json();
          
          const last = messagesEl.querySelectorAll('.msg.agent');
          if(last.length) last[last.length-1].remove();
          
          if(data.has_pdf && data.download_url){
            const msgDiv = document.createElement('div');
            msgDiv.className = 'msg agent';
            msgDiv.innerHTML = data.reply + '<br><br><button onclick="downloadPDF()" style="background:#0b5ed7;color:#fff;border:none;padding:10px 20px;border-radius:6px;cursor:pointer;">📥 Download PDF Report</button>';
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


@app.route('/mcp/servers', methods=['GET'])
def list_mcp_servers():
    """List all registered MCP servers"""
    servers_info = []
    for name, server in mcp_servers.items():
        servers_info.append(server.get_server_info())
    
    return jsonify({
        "total": len(servers_info),
        "servers": servers_info,
        "genai_enabled": genai_client is not None,
        "genai_region": genai_region
    })


@app.route('/chat', methods=['POST'])
def chat():
    """Handle chat requests with MCP routing"""
    logger.info("Received chat request")
    try:
        data = request.get_json()
        if not data:
            return jsonify({"reply": "⚠️ Error: Invalid request format"}), 400
        
        prompt = data.get('prompt', '')
        if not prompt or not isinstance(prompt, str):
            return jsonify({"reply": "⚠️ Error: Please provide a valid question"}), 400
        
        logger.info(f"Received prompt: {prompt}")
        
        # Route to MCP server
        result = route_to_mcp_server(prompt.strip())
        advisor = result['advisor']
        response = result['response']
        
        # Handle PDF downloads
        if "PDF_DOWNLOAD:" in response:
            parts = response.split("PDF_DOWNLOAD:")[1].strip().split(":", 1)
            if len(parts) == 2:
                advisor_name = parts[0]
                pdf_data = parts[1]
            else:
                advisor_name = "Finance"
                pdf_data = response.split("PDF_DOWNLOAD:")[1].strip()
            
            download_id = str(uuid.uuid4())
            download_storage[download_id] = {
                'type': 'pdf',
                'data': pdf_data,
                'advisor': advisor_name,
                'timestamp': datetime.now().strftime('%Y%m%d_%H%M%S')
            }
            logger.info(f"PDF stored with ID: {download_id}")
            
            response_text = f"🎯 {advisor}\n────────────────────────────\n📄 Your report is ready!\n\nClick the button below to download the PDF report."
            return jsonify({
                "reply": response_text,
                "has_pdf": True,
                "download_url": f"/download_pdf/{download_id}"
            })
        
        # Handle Report downloads
        if "REPORT_DOWNLOAD:" in response:
            download_marker = response.split("REPORT_DOWNLOAD:")[1].strip()
            parts = download_marker.split(":", 2)
            if len(parts) == 3:
                advisor_name = parts[0]
                report_format = parts[1].lower()
                report_data = parts[2]
                
                download_id = str(uuid.uuid4())
                download_storage[download_id] = {
                    'type': 'report',
                    'format': report_format,
                    'data': report_data,
                    'advisor': advisor_name,
                    'timestamp': datetime.now().strftime('%Y%m%d_%H%M%S')
                }
                logger.info(f"Report stored with ID: {download_id}")
                
                response_text = f"🎯 {advisor}\n────────────────────────────\n📊 Your analytics report is ready!\n\nClick the button below to download the {report_format.upper()} report."
                return jsonify({
                    "reply": response_text,
                    "has_pdf": True,
                    "download_url": f"/download_report/{download_id}"
                })
        
        # Format regular response
        formatted_response = f"🎯 {advisor}\n────────────────────────────\n{response}\n\n⏰ {datetime.now().strftime('%H:%M:%S')}"
        
        logger.info(f"Response generated by {advisor}")
        return jsonify({"reply": formatted_response})
        
    except Exception as e:
        logger.error(f"Error processing request: {e}", exc_info=True)
        return jsonify({"reply": "⚠️ An error occurred while processing your request."}), 500


@app.route('/download_pdf/<download_id>', methods=['GET'])
def download_pdf(download_id):
    """Download PDF report"""
    try:
        download_data = download_storage.get(download_id)
        if not download_data or download_data.get('type') != 'pdf':
            return "No PDF available", 404
        
        pdf_bytes = base64.b64decode(download_data['data'])
        timestamp = download_data.get('timestamp', datetime.now().strftime('%Y%m%d_%H%M%S'))
        filename = f"Finance_Report_{timestamp}.pdf"
        
        logger.info(f"Sending PDF download: {filename}")
        
        return send_file(
            BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        logger.error(f"Error downloading PDF: {e}", exc_info=True)
        return "Error downloading PDF", 500


@app.route('/download_report/<download_id>', methods=['GET'])
def download_report(download_id):
    """Download analytics report"""
    try:
        download_data = download_storage.get(download_id)
        if not download_data or download_data.get('type') != 'report':
            return "No report available", 404
        
        report_format = download_data.get('format', 'pdf')
        report_bytes = base64.b64decode(download_data['data'])
        
        format_mapping = {
            'pdf': ('application/pdf', 'pdf'),
            'png': ('image/png', 'png'),
            'xlsx': ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'xlsx'),
            'csv': ('text/csv', 'csv')
        }
        
        mimetype, extension = format_mapping.get(report_format, ('application/octet-stream', 'bin'))
        timestamp = download_data.get('timestamp', datetime.now().strftime('%Y%m%d_%H%M%S'))
        filename = f"Analytics_Report_{timestamp}.{extension}"
        
        logger.info(f"Sending report download: {filename}")
        
        return send_file(
            BytesIO(report_bytes),
            mimetype=mimetype,
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        logger.error(f"Error downloading report: {e}", exc_info=True)
        return "Error downloading report", 500


if __name__ == '__main__':
    logger.info("="*60)
    logger.info("RCOE Gen AI Agents - MCP Architecture")
    logger.info(f"Gen AI Region: {genai_region}")
    logger.info(f"MCP Servers: {list(mcp_servers.keys())}")
    logger.info(f"Intent Detection: {'Enabled' if genai_client else 'Disabled'}")
    logger.info("="*60)
    app.run(host='0.0.0.0', port=5001)
