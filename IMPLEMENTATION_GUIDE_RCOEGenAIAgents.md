# Implementation Guide - RCOE Gen AI Advisor Systems (OCI Gen AI & MCP)

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Prerequisites](#prerequisites)
3. [Step-by-Step Implementation](#step-by-step-implementation)
4. [MCP Server Development](#mcp-server-development)
5. [OCI Gen AI Integration](#oci-gen-ai-integration)
6. [API Integrations](#api-integrations)
7. [Testing & Validation](#testing--validation)
8. [Deployment](#deployment)
9. [Monitoring & Maintenance](#monitoring--maintenance)
10. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

### System Components

```
┌───────────────────────────────────────────────────────────────┐
│                      Frontend (HTML/JS)                        │
│  • Chat interface                                              │
│  • Sample question buttons                                     │
│  • Download handlers                                           │
└───────────────────────────────────────────────────────────────┘
                              │
                              ▼ HTTP POST /chat
┌───────────────────────────────────────────────────────────────┐
│              RCOEGenAIAgents.py (Flask App)                    │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │   detect_intent_with_genai(prompt)                      │  │
│  │   • Calls OCI Gen AI with classification prompt         │  │
│  │   • Returns: general|finance|hr|orders|reports          │  │
│  └─────────────────────────────────────────────────────────┘  │
│                              │                                 │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │   route_to_mcp_server(prompt, intent)                   │  │
│  │   • Selects appropriate MCP server                      │  │
│  │   • Calls server.handle_request(prompt)                 │  │
│  └─────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌──────────────┐      ┌──────────────┐     ┌──────────────┐
│ mcp_servers/ │      │ mcp_servers/ │     │ mcp_servers/ │
│ base_server  │      │  advisors    │     │  advisors    │
│    .py       │◄─────│  .py         │     │  .py         │
└──────────────┘      └──────────────┘     └──────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
  GeneralMCP           FinanceMCP            ReportsMCP
   Server               Server                 Server
        │                     │                     │
        ▼                     ▼                     ▼
   ORDS GenAI          BI Publisher            OAC Export
    Module              SOAP API                  API
```

### Design Principles

1. **Separation of Concerns**: Each advisor is a self-contained MCP server
2. **Single Responsibility**: One server handles one domain
3. **Open/Closed**: Easy to add new advisors without modifying existing code
4. **Dependency Injection**: Config and API specs injected into servers
5. **Pure Intent Routing**: No keyword fallback, Gen AI only

---

## Prerequisites

### 1. Development Environment

```bash
# Python 3.8 or higher
python --version

# Virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac
```

### 2. Required Python Packages

```bash
pip install flask==3.0.0
pip install python-dotenv==1.0.0
pip install requests==2.31.0
pip install oci==2.119.1
```

### 3. OCI Setup

#### Create OCI API Key

```bash
# Generate API key pair
mkdir ~/.oci
openssl genrsa -out ~/.oci/oci_api_key.pem 2048
openssl rsa -pubout -in ~/.oci/oci_api_key.pem -out ~/.oci/oci_api_key_public.pem

# Get fingerprint
openssl rsa -pubout -outform DER -in ~/.oci/oci_api_key.pem | openssl md5 -c
```

#### Upload Public Key to OCI Console

1. Log in to OCI Console
2. Navigate to: User Settings → API Keys
3. Click "Add API Key"
4. Upload `oci_api_key_public.pem`
5. Copy the configuration preview

#### Enable Gen AI Service

1. Navigate to: Analytics & AI → Generative AI
2. Ensure service is enabled in **us-chicago-1** region
3. Verify access to `cohere.command-plus-latest` model

### 4. Backend API Access

Ensure you have credentials for:
- Oracle APEX/ORDS GenAI Module
- BI Publisher SOAP endpoint
- Oracle Fusion SCM REST API
- Oracle Analytics Cloud Export API

---

## Step-by-Step Implementation

### Step 1: Project Structure Setup

```
OCI_Bot/
├── RCOEGenAIAgents.py              # Main Flask application
├── mcp_servers/
│   ├── __init__.py                  # Package marker
│   ├── base_server.py               # MCPServer abstract base class
│   └── advisors.py                  # 5 MCP server implementations
├── config.properties                # Application configuration
├── .env                             # OCI credentials (DO NOT COMMIT)
├── api_spec_general.json            # ORDS GenAI spec
├── api_spec_finance.json            # BI Publisher SOAP spec
├── api_spec_hr.json                 # ORDS GenAI spec
├── api_spec_orders.json             # Fusion SCM REST spec
├── api_spec_reports.json            # OAC Export spec
├── requirements.txt                 # Python dependencies
└── rcoe_genai_agents.log           # Application logs
```

### Step 2: Configure Environment Variables

Create `.env` file:

```properties
# OCI Authentication
OCI_USER=ocid1.user.oc1..aaaaaaaa...
OCI_FINGERPRINT=aa:bb:cc:dd:ee:ff:00:11:22:33:44:55:66:77:88:99
OCI_TENANCY=ocid1.tenancy.oc1..aaaaaaaa...
OCI_KEY_FILE=~/.oci/oci_api_key.pem
```

⚠️ **Security**: Add `.env` to `.gitignore`

### Step 3: Configure Application Settings

Edit `config.properties`:

```properties
# OCI Gen AI Configuration
genai_region=us-chicago-1
genai_intent_mode=force              # force (always use GenAI) | auto | off

# API Settings
use_mock_responses=false             # Set true for testing without APIs
api_timeout=30
api_retry_count=3
api_retry_delay=1

# General Agent (ORDS GenAI Module)
general_agent_url=https://your-ords-url/ords/user/genai_module/query
general_agent_username=
general_agent_password=

# Finance Agent (BI Publisher SOAP)
finance_agent_url=https://your-bi-publisher/xmlpserver/services/ExternalReportWSSService
finance_agent_username=your_bi_user
finance_agent_password=your_bi_password

# HR Agent (ORDS GenAI Module)
hr_agent_url=https://your-ords-url/ords/user/genai_module/query
hr_agent_username=
hr_agent_password=

# Orders Agent (Fusion SCM REST)
orders_agent_url=https://your-fusion-scm/fscmRestApi/resources/11.13.18.05/salesOrdersForOrderHub
orders_agent_username=your_fusion_user
orders_agent_password=your_fusion_password

# Reports Agent (OAC Export)
reports_agent_url=https://your-oac-instance.analytics.ocp.oraclecloud.com
reports_agent_username=your_oac_user
reports_agent_password=your_oac_password
```

### Step 4: Create API Specifications

Each API spec defines the contract for backend integration.

**Example: `api_spec_finance.json`**

```json
{
  "name": "Finance BI Publisher API",
  "version": "1.0",
  "type": "SOAP",
  "endpoint": "xmlpserver/services/ExternalReportWSSService",
  "authentication": "Basic",
  "operations": {
    "runReport": {
      "method": "POST",
      "soapAction": "",
      "parameters": {
        "reportAbsolutePath": "/Custom/ROIC/ROIC_PO_REPORTS.xdo",
        "attributeFormat": "pdf",
        "parameterNameValues": {
          "P_PO_NUM": "55269"
        }
      },
      "response": {
        "format": "base64",
        "field": "reportBytes"
      }
    }
  }
}
```

---

## MCP Server Development

### Base MCP Server Class

**File: `mcp_servers/base_server.py`**

```python
from abc import ABC, abstractmethod
from datetime import datetime
import logging

class MCPServer(ABC):
    """Abstract base class for MCP servers"""
    
    def __init__(self, config: dict, api_spec: dict):
        self.config = config
        self.api_spec = api_spec
        self.name = "Base MCP Server"
        self.status = "not_registered"
        self.registered_at = None
        self.logger = logging.getLogger(__name__)
    
    def register(self) -> bool:
        """Register the MCP server"""
        try:
            self.status = "registered"
            self.registered_at = datetime.now().isoformat()
            self.logger.info(f"[{self.name}] MCP server registered successfully")
            return True
        except Exception as e:
            self.logger.error(f"[{self.name}] Registration failed: {e}")
            self.status = "failed"
            return False
    
    def unregister(self) -> bool:
        """Unregister the MCP server"""
        self.status = "unregistered"
        return True
    
    @abstractmethod
    def handle_request(self, query: str) -> str:
        """
        Handle incoming request
        Must be implemented by concrete MCP servers
        """
        pass
    
    def get_server_info(self) -> dict:
        """Get server metadata"""
        return {
            "name": self.name,
            "status": self.status,
            "registered_at": self.registered_at
        }
```

### Implementing a Concrete MCP Server

**Example: Finance MCP Server**

```python
from mcp_servers.base_server import MCPServer
import requests
from requests.auth import HTTPBasicAuth
import base64
import re

class FinanceMCPServer(MCPServer):
    """Finance Advisor MCP Server - BI Publisher Integration"""
    
    def __init__(self, config: dict, api_spec: dict):
        super().__init__(config, api_spec)
        self.name = "Finance Advisor"
        
    def handle_request(self, query: str) -> str:
        """Process finance-related queries"""
        self.logger.info(f"[{self.name} MCP] Processing request")
        
        # Check if mock mode
        if self.config.get('use_mock_responses', 'false').lower() == 'true':
            return "Mock: Finance report generated successfully"
        
        # Call BI Publisher SOAP API
        try:
            response = self._call_bi_publisher_api()
            return response
        except Exception as e:
            self.logger.error(f"[{self.name} MCP] Error: {e}")
            return f"Finance API error: {str(e)}"
    
    def _call_bi_publisher_api(self) -> str:
        """Call BI Publisher SOAP API to generate report"""
        url = self.config.get('finance_agent_url')
        username = self.config.get('finance_agent_username')
        password = self.config.get('finance_agent_password')
        
        # SOAP request body
        soap_body = '''<?xml version="1.0" encoding="UTF-8"?>
        <soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
           <soap:Body>
              <pub:runReport xmlns:pub="http://xmlns.oracle.com/oxp/service/PublicReportService">
                 <pub:reportRequest>
                    <pub:attributeFormat>pdf</pub:attributeFormat>
                    <pub:reportAbsolutePath>/Custom/ROIC/ROIC_PO_REPORTS.xdo</pub:reportAbsolutePath>
                 </pub:reportRequest>
              </pub:runReport>
           </soap:Body>
        </soap:Envelope>'''
        
        headers = {"Content-Type": "application/soap+xml; charset=UTF-8"}
        auth = HTTPBasicAuth(username, password)
        
        response = requests.post(url, data=soap_body, headers=headers, auth=auth, timeout=30)
        
        if response.status_code == 200:
            # Extract base64 PDF from SOAP response
            match = re.search(r'<[^:]+:reportBytes>([^<]+)</[^:]+:reportBytes>', response.text)
            if match:
                pdf_data = match.group(1).strip()
                return f"PDF_DOWNLOAD:Finance:{pdf_data}"
        
        return f"BI Publisher API error: HTTP {response.status_code}"
```

### Key Implementation Patterns

#### 1. **Constructor Pattern**
```python
def __init__(self, config: dict, api_spec: dict):
    super().__init__(config, api_spec)
    self.name = "Your Server Name"
```

#### 2. **Request Handler Pattern**
```python
def handle_request(self, query: str) -> str:
    # 1. Log the request
    # 2. Check mock mode
    # 3. Call backend API
    # 4. Format response
    # 5. Return result
```

#### 3. **API Call Pattern**
```python
def _call_backend_api(self) -> str:
    # 1. Get credentials from config
    # 2. Prepare request
    # 3. Make HTTP call
    # 4. Parse response
    # 5. Return formatted data
```

#### 4. **Download Marker Pattern**
For binary downloads (PDF, reports):
```python
return f"PDF_DOWNLOAD:AdvisorName:{base64_data}"
return f"REPORT_DOWNLOAD:AdvisorName:FORMAT:{base64_data}"
```

---

## OCI Gen AI Integration

### Intent Classification Prompt

The key to accurate routing is a well-crafted classification prompt:

```python
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
```

### Gen AI Client Initialization

```python
from oci.generative_ai_inference import GenerativeAiInferenceClient
from oci.generative_ai_inference.models import (
    OnDemandServingMode,
    ChatDetails,
    CohereChatRequest
)

# Initialize client
oci_config = {
    'user': os.getenv('OCI_USER'),
    'key_file': os.path.expanduser(os.getenv('OCI_KEY_FILE')),
    'fingerprint': os.getenv('OCI_FINGERPRINT'),
    'tenancy': os.getenv('OCI_TENANCY'),
    'region': CONFIG.get('genai_region', 'us-chicago-1')
}

genai_client = GenerativeAiInferenceClient(
    config=oci_config,
    service_endpoint=f"https://inference.generativeai.{genai_region}.oci.oraclecloud.com"
)
```

### Making Intent Detection Calls

```python
def detect_intent_with_genai(prompt: str) -> Optional[str]:
    chat_request = CohereChatRequest(
        message=classification_prompt,
        max_tokens=10,
        temperature=0.1,  # Low for consistent classification
        frequency_penalty=0,
        top_p=0.75,
        top_k=0
    )
    
    chat_details = ChatDetails(
        serving_mode=OnDemandServingMode(model_id='cohere.command-plus-latest'),
        compartment_id=os.getenv('OCI_TENANCY'),
        chat_request=chat_request
    )
    
    response = genai_client.chat(chat_details)
    
    if response.data and response.data.chat_response:
        intent = response.data.chat_response.text.strip().lower()
        
        # Validate against known intents
        valid_intents = ['general', 'finance', 'hr', 'orders', 'reports']
        if intent in valid_intents:
            return intent
    
    return None
```

---

## API Integrations

### 1. ORDS GenAI Module (General & HR)

**Request:**
```python
params = {"prompt": query}
response = requests.get(
    url=ords_url,
    params=params,
    headers={"Accept": "application/json"},
    auth=HTTPBasicAuth(username, password),
    timeout=30
)
```

**Response Handling:**
```python
if response.status_code == 200:
    data = response.json()
    
    # Handle array response
    if isinstance(data, list):
        if len(data) > 10:
            # Paginate
            return format_top_10(data)
        else:
            return format_all(data)
    
    # Handle object response
    return data.get('query_result', data)
```

### 2. BI Publisher SOAP (Finance)

**SOAP Request:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" 
               xmlns:pub="http://xmlns.oracle.com/oxp/service/PublicReportService">
   <soap:Body>
      <pub:runReport>
         <pub:reportRequest>
            <pub:attributeFormat>pdf</pub:attributeFormat>
            <pub:reportAbsolutePath>/Custom/Reports/MyReport.xdo</pub:reportAbsolutePath>
            <pub:parameterNameValues>
               <pub:item>
                  <pub:name>PARAM_NAME</pub:name>
                  <pub:values><pub:item>VALUE</pub:item></pub:values>
               </pub:item>
            </pub:parameterNameValues>
         </pub:reportRequest>
      </pub:runReport>
   </soap:Body>
</soap:Envelope>
```

**Parse Response:**
```python
import re

match = re.search(r'<[^:]+:reportBytes>([^<]+)</[^:]+:reportBytes>', response.text)
if match:
    pdf_base64 = match.group(1).strip()
    return f"PDF_DOWNLOAD:Finance:{pdf_base64}"
```

### 3. Fusion SCM REST (Orders)

**List Orders:**
```python
params = {"limit": 10}
response = requests.get(
    url=f"{base_url}/salesOrdersForOrderHub",
    params=params,
    headers={"Accept": "application/json"},
    auth=HTTPBasicAuth(username, password)
)

data = response.json()
items = data.get('items', [])

# Sort by latest date
items_sorted = sorted(
    items, 
    key=lambda x: x.get('LastUpdateDate', ''), 
    reverse=True
)
```

**Get Specific Order:**
```python
# Extract order key from query (e.g., "OPS:300000203741093")
order_key = extract_order_key(query)

response = requests.get(
    url=f"{base_url}/salesOrdersForOrderHub/{order_key}",
    headers={"Accept": "application/json"},
    auth=HTTPBasicAuth(username, password)
)

order_data = response.json()
return format_order_details(order_data)
```

### 4. Oracle Analytics Cloud (Reports)

**2-Step Process (No Status Polling):**

**Step 1: Initiate Export**
```python
export_url = f"{base_url}/api/20210901/catalog/workbooks/{workbook_id}/exports"
payload = {
    "name": "Absence Workbook Report",
    "type": "file",
    "canvasIds": ["snapshot!canvas!1"],
    "format": "pdf",
    "screenwidth": 1440,
    "screenheight": 900
}

response = requests.post(export_url, json=payload, auth=auth)
# Parse exportId from resourceUri field
resource_uri = response.json()['resourceUri']
export_id = resource_uri.split('/exports/')[-1]
```

**Step 2: Wait and Download with Retries**
```python
# Wait 30 seconds for export job to complete
time.sleep(30)

# Attempt download with up to 3 retries
download_url = f"{base_url}/api/20210901/catalog/workbooks/{workbook_id}/exports/{export_id}"
max_attempts = 3

for attempt in range(max_attempts):
    download_response = requests.get(download_url, auth=auth, timeout=30)
    
    if download_response.status_code == 200:
        report_base64 = base64.b64encode(download_response.content).decode('utf-8')
        return f"REPORT_DOWNLOAD:Reports:PDF:{report_base64}"
    
    # Wait 10 seconds before retry (if not last attempt)
    if attempt < max_attempts - 1:
        time.sleep(10)

# If all retries fail
raise Exception("Report download failed after all retry attempts")
```

**Key Changes:**
- **No status polling**: Removed intermediate status check endpoint
- **30-second wait**: Single wait period after export initiation
- **3 download retries**: Direct download attempts with 10-second intervals
- **Enhanced payload**: Includes name, type, canvasIds, screenwidth, and screenheight
- **exportId extraction**: Parsed from resourceUri response field

---

## Testing & Validation

### Unit Testing MCP Servers

**Test File: `test_mcp_servers.py`**

```python
import unittest
from mcp_servers.advisors import FinanceMCPServer

class TestFinanceMCPServer(unittest.TestCase):
    
    def setUp(self):
        self.config = {
            'use_mock_responses': 'true',
            'finance_agent_url': 'https://test.example.com',
            'finance_agent_username': 'test',
            'finance_agent_password': 'test'
        }
        self.api_spec = {}
        self.server = FinanceMCPServer(self.config, self.api_spec)
    
    def test_registration(self):
        result = self.server.register()
        self.assertTrue(result)
        self.assertEqual(self.server.status, 'registered')
    
    def test_handle_request_mock(self):
        response = self.server.handle_request("Show me finance reports")
        self.assertIsNotNone(response)
        self.assertIn("Mock", response)
    
    def test_server_info(self):
        self.server.register()
        info = self.server.get_server_info()
        self.assertEqual(info['name'], 'Finance Advisor')
        self.assertEqual(info['status'], 'registered')
```

### Integration Testing

**Test Gen AI Intent Detection:**

```python
def test_intent_detection():
    test_cases = [
        ("Show me finance reports", "finance"),
        ("List all employees", "hr"),
        ("What are recent orders?", "orders"),
        ("Export analytics dashboard", "reports"),
        ("What can you do?", "general")
    ]
    
    for query, expected_intent in test_cases:
        detected = detect_intent_with_genai(query)
        print(f"Query: {query}")
        print(f"Expected: {expected_intent}, Got: {detected}")
        assert detected == expected_intent, f"Intent mismatch for: {query}"
```

### End-to-End Testing

```bash
# Start the application
python RCOEGenAIAgents.py

# In another terminal, run tests
curl -X POST http://localhost:5000/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Show me financial reports"}'

# Expected: Routes to Finance Advisor
```

**Verify MCP Server Status:**
```bash
curl http://localhost:5000/mcp/servers
```

Expected output:
```json
{
  "total": 5,
  "servers": [
    {"name": "General Agent", "status": "registered"},
    {"name": "Finance Advisor", "status": "registered"},
    {"name": "HR Advisor", "status": "registered"},
    {"name": "Orders Advisor", "status": "registered"},
    {"name": "Reports Advisor", "status": "registered"}
  ],
  "genai_enabled": true,
  "genai_region": "us-chicago-1"
}
```

---

## Deployment

### Production Checklist

- [ ] Remove `use_mock_responses=true` from config
- [ ] Set `DEBUG=False` in Flask
- [ ] Use HTTPS for all API endpoints
- [ ] Store credentials in OCI Vault (not .env)
- [ ] Implement download storage cleanup (TTL)
- [ ] Add rate limiting
- [ ] Configure CORS appropriately
- [ ] Set up monitoring and alerting
- [ ] Enable SSL/TLS certificates
- [ ] Configure firewall rules
- [ ] Set up log rotation
- [ ] Document disaster recovery plan

### Docker Deployment

**Dockerfile:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["python", "RCOEGenAIAgents.py"]
```

**Build and Run:**
```bash
docker build -t rcoe-genai-agents .
docker run -p 5000:5000 \
  --env-file .env \
  -v $(pwd)/config.properties:/app/config.properties \
  rcoe-genai-agents
```

### Cloud Deployment (OCI)

**Deploy to OCI Container Instances:**

```bash
# Push to OCI Registry
docker tag rcoe-genai-agents:latest \
  <region>.ocir.io/<tenancy>/rcoe-genai-agents:latest

docker push <region>.ocir.io/<tenancy>/rcoe-genai-agents:latest

# Create Container Instance
oci container-instances container-instance create \
  --compartment-id <compartment-ocid> \
  --containers file://container-config.json \
  --shape CI.Standard.E4.Flex \
  --shape-config '{"ocpus":1,"memoryInGBs":4}'
```

---

## Monitoring & Maintenance

### Logging Strategy

**Log Levels:**
- **INFO**: Normal operations, server registration, routing decisions
- **WARNING**: Fallbacks, non-critical errors
- **ERROR**: API failures, Gen AI errors
- **DEBUG**: Request/response details (disable in production)

**Log Analysis:**
```bash
# Count requests per advisor
grep "\[Routing\] Routing to MCP server:" rcoe_genai_agents.log | \
  awk -F': ' '{print $NF}' | sort | uniq -c

# Find Gen AI failures
grep "Gen AI intent detection failed" rcoe_genai_agents.log

# Track response times
grep "Processing request" rcoe_genai_agents.log | \
  awk '{print $1, $2, $NF}'
```

### Metrics to Monitor

1. **Intent Detection Accuracy**
   - % of successful Gen AI classifications
   - Fallback to General advisor rate

2. **MCP Server Health**
   - Registration success rate
   - Request processing time
   - Error rate per advisor

3. **API Integration Health**
   - API response times
   - Authentication failures
   - Timeout occurrences

4. **Resource Usage**
   - Memory for download storage
   - CPU during Gen AI calls
   - Network bandwidth

### Maintenance Tasks

**Daily:**
- Review error logs
- Check disk space for logs
- Verify Gen AI service availability

**Weekly:**
- Analyze intent detection patterns
- Review API performance metrics
- Clean up old download storage

**Monthly:**
- Update OCI SDK: `pip install --upgrade oci`
- Review and rotate API credentials
- Performance tuning based on metrics
- Update API specifications if backends change

---

## Troubleshooting

### Common Issues

#### Issue 1: Gen AI Returns Wrong Intent

**Symptoms:**
- Finance queries route to General
- Mixed routing behavior

**Diagnosis:**
```python
# Check logs for intent detection
grep "Gen AI detected intent" rcoe_genai_agents.log
```

**Solutions:**
1. Refine classification prompt with more examples
2. Adjust temperature (lower = more consistent)
3. Check for ambiguous queries
4. Add query preprocessing/normalization

#### Issue 2: MCP Server Registration Fails

**Symptoms:**
- Less than 5 servers in `/mcp/servers`
- Startup errors

**Diagnosis:**
```python
# Check registration logs
grep "MCP server registered" rcoe_genai_agents.log
grep "Registration failed" rcoe_genai_agents.log
```

**Solutions:**
1. Verify config.properties syntax
2. Check API endpoint accessibility
3. Validate credentials
4. Enable mock mode to isolate issue

#### Issue 3: Download Not Working

**Symptoms:**
- PDF download fails
- Empty file downloaded

**Diagnosis:**
```python
# Check download storage
grep "PDF stored" rcoe_genai_agents.log
grep "download_storage" rcoe_genai_agents.log
```

**Solutions:**
1. Check base64 encoding integrity
2. Verify MIME type in response
3. Inspect browser network tab
4. Check server memory limits

#### Issue 4: API Timeout

**Symptoms:**
- "API timeout" errors
- Slow responses

**Diagnosis:**
```python
# Check timeout logs
grep "timeout" rcoe_genai_agents.log
```

**Solutions:**
1. Increase `api_timeout` in config.properties
2. Check network connectivity to backend
3. Optimize API queries (add filters, pagination)
4. Enable retry logic with exponential backoff

---

## Advanced Topics

### Adding a New MCP Server

**Step 1:** Create server class in `mcp_servers/advisors.py`

```python
class CustomMCPServer(MCPServer):
    def __init__(self, config: dict, api_spec: dict):
        super().__init__(config, api_spec)
        self.name = "Custom Advisor"
    
    def handle_request(self, query: str) -> str:
        # Your implementation
        return "Custom response"
```

**Step 2:** Load API spec in `RCOEGenAIAgents.py`

```python
API_SPEC_CUSTOM = load_api_spec('api_spec_custom.json')
```

**Step 3:** Register server

```python
custom_server = CustomMCPServer(CONFIG, API_SPEC_CUSTOM)
if custom_server.register():
    mcp_servers['custom'] = custom_server
```

**Step 4:** Update intent classification prompt

```python
classification_prompt = f"""...
Available advisors:
- general: ...
- finance: ...
- custom: Your custom advisor description
..."""
```

### Performance Optimization

**1. Caching Intent Results:**
```python
from functools import lru_cache

@lru_cache(maxsize=100)
def detect_intent_cached(prompt_hash: str) -> Optional[str]:
    return detect_intent_with_genai(prompt_hash)
```

**2. Async API Calls:**
```python
import asyncio
import aiohttp

async def call_api_async(url, payload):
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            return await response.json()
```

**3. Connection Pooling:**
```python
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

session = requests.Session()
retry = Retry(total=3, backoff_factor=1)
adapter = HTTPAdapter(max_retries=retry)
session.mount('https://', adapter)
```

---

## Appendix

### A. Configuration Reference

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `genai_region` | string | us-chicago-1 | OCI Gen AI region |
| `genai_intent_mode` | string | auto | force\|auto\|off |
| `use_mock_responses` | boolean | false | Enable mock mode |
| `api_timeout` | integer | 30 | API timeout in seconds |
| `api_retry_count` | integer | 3 | Number of retry attempts |
| `api_retry_delay` | integer | 1 | Delay between retries (seconds) |

### B. API Spec Schema

```json
{
  "name": "API Name",
  "version": "1.0",
  "type": "REST|SOAP|GraphQL",
  "endpoint": "base/path",
  "authentication": "Basic|Bearer|APIKey",
  "operations": {
    "operationName": {
      "method": "GET|POST|PUT|DELETE",
      "path": "/specific/path",
      "parameters": {},
      "response": {
        "format": "json|xml|binary",
        "schema": {}
      }
    }
  }
}
```

### C. Error Codes

| Code | Description | Resolution |
|------|-------------|------------|
| 401 | Authentication failed | Check credentials in config |
| 404 | Resource not found | Verify endpoint URL |
| 500 | Server error | Check backend logs |
| 503 | Service unavailable | Check backend service status |
| Timeout | Request timeout | Increase api_timeout |

### D. Resources

- **OCI Gen AI Documentation**: https://docs.oracle.com/en-us/iaas/Content/generative-ai/home.htm
- **Flask Documentation**: https://flask.palletsprojects.com/
- **OCI Python SDK**: https://oracle-cloud-infrastructure-python-sdk.readthedocs.io/
- **Model Context Protocol**: https://modelcontextprotocol.io/

---

**Document Version:** 1.0  
**Last Updated:** November 11, 2025  
**Author:** Ramsiit2010
