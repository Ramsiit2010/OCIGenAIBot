# Enterprise Advisory Chat Bot

A Flask-based interactive chat app with specialized advisors for General, Finance, HR, Orders, and Reports. Integrates with Oracle APEX/ORDS (General/HR), Oracle Fusion BI Publisher SOAP (Finance, PDF reports), Oracle Fusion Cloud SCM REST (Orders), and Oracle Analytics Cloud Workbook Export (Reports). Supports optional OCI Generative AI intent detection (Chicago region) with keyword fallback.

## 🌟 Features

- Multi-Advisor System: Specialized responses from General, Finance, HR, Orders, and Reports advisors
- Hybrid API Integration:
    - General & HR: Oracle APEX/ORDS GenAI Module (GET with prompt)
    - Finance: Oracle Fusion BI Publisher SOAP ExternalReportWSSService (base64 PDF)
    - Orders: Oracle Fusion Cloud SCM REST (Sales Orders list/detail)
    - Reports: Oracle Analytics Cloud Workbook Export (poll and download)
- Intent Routing (dual mode):
    - OCI Gen AI (Chicago) classification → primary (configurable)
    - Keyword-based routing → reliable fallback
- Server-side download storage: Avoids cookie limits; robust retryable downloads
- Interactive UI with sample prompts and clean formatting
- Real-time responses with advisor-specific hints
- Logging System: Detailed INFO logs to console and app.log
- Pagination UX: Lists show first 10 items with "showing 10 of N" hint

- Multi-Advisor System: Specialized responses from General, Finance, HR, Orders, and Reports advisors
- Hybrid API Integration:
    - General & HR: Oracle APEX/ORDS GenAI Module (GET with prompt)
    - Finance: Oracle Fusion BI Publisher SOAP ExternalReportWSSService (base64 PDF)
    - Orders: Oracle Fusion Cloud SCM REST (Sales Orders list/detail)
    - Reports: Oracle Analytics Cloud Workbook Export (30s wait + 3 retry downloads)
- Intent Routing (dual mode):
    - OCI Gen AI (Chicago) classification → primary (configurable)
    - Keyword-based routing → reliable fallback
- Server-side download storage: Avoids cookie limits; robust retryable downloads
- Interactive UI with sample prompts and clean formatting
- Real-time responses with advisor-specific hints
- Logging System: Detailed INFO logs to console and app.log
- Pagination UX: Lists show first 10 items with “showing 10 of N” hint

## 🚀 Quick Start

### Prerequisites

- Python 3.11+ (tested on 3.12)
- Install from requirements.txt

### Installation

1. Clone the repository

```bash
git clone <repository-url>
cd OCI_Bot
```

1. (Recommended) Create and activate a virtual environment

On Windows PowerShell:

```powershell
python -m venv .venv
./.venv/Scripts/Activate.ps1
```

1. Install required packages
3. Install required packages

```powershell
pip install -r requirements.txt
```

1. Configure your agents

         - Edit `config.properties`:
             - General & HR: ORDS GenAI Module `/query` endpoint, optional Basic Auth
             - Finance: BI Publisher SOAP `/xmlpserver/services/ExternalReportWSSService` with Basic Auth
             - Orders: Fusion SCM REST `.../fscmRestApi/resources/11.13.18.05/salesOrdersForOrderHub` with Basic Auth
             - Reports: OAC workbook export base URL
             - Optional: `genai_intent_mode=auto|force|off` (intent routing mode)
             - Set `use_mock_responses=false` when ready to use real APIs
         - Review API specifications in `api_spec_*.json` files
         - Create `.env` with OCI credentials for Gen AI (see below)

1. Run the application (Windows PowerShell)

```powershell
C:/Softwares/OCI_Bot/.venv/Scripts/python.exe .\AskMeChatBot.py
```

1. Access the chat interface at `http://localhost:5000`

## 💡 Usage

- General: Capabilities, guidance, routing help
- Finance: BI Publisher report generation; returns a PDF with download button
- HR: Company policies, benefits, leave management
- Orders: Oracle Fusion Sales Orders (list vs. detail)
- Reports: OAC workbook export (PDF/other formats)

The chat bot supports queries related to:

Orders behavior:

- If your prompt includes an OrderKey (e.g., OPS:300000203741093) or a long numeric ID (9–15 digits), the app calls the detail endpoint `/salesOrdersForOrderHub/{OrderKeyOrId}`.
- Otherwise, it calls the list endpoint with `limit=10` and sorts results by latest `LastUpdateDate`.

Sample questions are provided in the UI for quick testing.

Intent routing:
- If OCI Gen AI is enabled and reachable, the app first attempts single-advisor intent classification (Chicago region) and routes accordingly (mode = `auto` or `force`).
- If detection is disabled or inconclusive, keyword-based routing runs and may invoke multiple advisors when multiple domains are detected.

## 🔧 Customization Guide

### Configuration Files

The application uses the following configuration files:

1. **`config.properties`** - Main configuration file
    - General & HR: ORDS GenAI Module URLs and optional Basic Auth
    - Finance: BI Publisher SOAP URL and credentials
    - Orders: Fusion SCM REST URL and credentials
    - Reports: OAC base URL and credentials
    - Controls mock vs. real calls, API timeout, retries, and `genai_intent_mode` (auto/force/off)

2. **API Specification Files**
   - `api_spec_general.json` - General agent API specification
   - `api_spec_finance.json` - Finance agent API specification
   - `api_spec_hr.json` - HR agent API specification
   - `api_spec_orders.json` - Orders agent API specification

### Switching from Mock to Real APIs

1. Edit `config.properties`:

```properties
# Enable real API calls
use_mock_responses=false

# General & HR (ORDS)
general_agent_url=https://<ords-host>/ords/.../genai_module/query
hr_agent_url=https://<ords-host>/ords/.../genai_module/query

# Finance (BI Publisher SOAP)
finance_agent_url=https://<fusion-host>/xmlpserver/services/ExternalReportWSSService
finance_agent_username=<username>
finance_agent_password=<password>

# Orders (Fusion SCM REST)
orders_agent_url=https://<fusion-host>/fscmRestApi/resources/11.13.18.05/salesOrdersForOrderHub
orders_agent_username=<username>
orders_agent_password=<password>

# Reports (Oracle Analytics Cloud)
reports_agent_url=https://<oac-host>
reports_agent_username=<username>
reports_agent_password=<password>

# Intent routing
genai_intent_mode=auto  # options: auto | force | off
```

API specifics:

    - General/HR (ORDS): GET `/query?prompt=...`; JSON may include `query_result`, `response`, `reply`, or `answer`.
    - Finance (BI Publisher SOAP): POST SOAP XML to `/xmlpserver/services/ExternalReportWSSService`; returns `<reportBytes>` (base64 PDF). The UI exposes a "Download PDF Report" button.
    - Orders (Fusion SCM REST):
        - List: GET `/salesOrdersForOrderHub?limit=10` then sort by latest `LastUpdateDate` client-side.
        - Detail: GET `/salesOrdersForOrderHub/{OrderKeyOrId}` when prompt contains an OrderKey or long numeric ID.
    - Reports (OAC Workbook Export): Initiate export → wait 30s → download with 3 retry attempts (10s intervals).

Restart the application to load new configuration

### OCI Generative AI (.env)

Provide OCI credentials used to initialize the Generative AI Inference client (Chicago region):

```env
OCI_USER=ocid1.user.oc1..xxxx
OCI_KEY_FILE=~/.oci/oci_api_key.pem
OCI_FINGERPRINT=aa:bb:cc:...
OCI_TENANCY=ocid1.tenancy.oc1..xxxx
OCI_REGION=us-chicago-1
```

Notes:
- The client is created against `https://inference.generativeai.us-chicago-1.oci.oraclecloud.com`.
- Set `genai_intent_mode=auto|force|off` in `config.properties` to control usage.

### Modifying Mock Responses

To replace mock responses with real API endpoints, modify the following sections:

1. **Mock Response Data** (Lines 27-46):

```python
MOCK_RESPONSES = {
    "finance": {
        "revenue": "Your response here",
        "expenses": "Your response here",
        "budget": "Your response here",
    },
    # ... other sections
}
```

1. **Advisor Functions**:
 
Replace mock logic or wire your API calls as needed:

```python
def get_finance_advice(query: str) -> str:
    # Replace with your API call
    api_response = your_api_client.get_finance_data(query)
    return format_api_response(api_response)
```

### Adding New Advisors

1. Add new advisor keywords in `process_user_query` (Lines ~200):

```python
advisor_keywords = {
    'your_new_advisor': ['keyword1', 'keyword2', ...]
}
```

1. Create a new advisor function:

```python
def get_new_advisor_advice(query: str) -> str:
    # Your implementation here
    return response
```

### Modifying Response Format

Update the `format_response` function to change response formatting:

```python
def format_response(result: Dict) -> str:
    # Customize your response format
    formatted_result = ...
    return formatted_result
```

## 🔒 Security Considerations

When implementing real API endpoints:

1. Use environment variables for sensitive data
2. Implement proper authentication
3. Add request rate limiting
4. Validate and sanitize user input

Example secure configuration:

```python
from os import environ
from dotenv import load_dotenv

load_dotenv()

API_KEY = environ.get('API_KEY')
API_ENDPOINT = environ.get('API_ENDPOINT')
```

## 📊 Logging

The application logs activities to:

- Console (INFO level)
- `app.log` file

Key run-time lines:

- `OCI Gen AI client initialized successfully for Chicago region`
- `Gen AI intent routing mode: auto|force|off`
- (When active) `Attempting OCI Gen AI intent detection...` and `Gen AI detection result: <intent>`
- Fallback path: `Using keyword-based routing (Gen AI not available or failed)`

To modify logging, update the configuration in the initialization section:

```python
logging.basicConfig(
    filename='app.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
```

## 🎨 UI Customization

The UI template is embedded in the `template` variable. Modify the HTML and CSS to customize the appearance:

- Change colors in the CSS section
- Modify layout and styling
- Add new UI elements

## 📝 License

[Your License Here]

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

## 📞 Support

Last updated: November 10, 2025

[Your Support Information]
