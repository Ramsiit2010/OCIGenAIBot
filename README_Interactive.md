# AskMeChatBot Interactive - Dynamic Parameter Collection

## Overview
Enhanced version of AskMeChatBot with **intelligent parameter extraction** and dynamic user interaction. Automatically detects required parameters from user queries using pattern matching and API spec defaults.

## Key Features

### 1. **Intelligent Parameter Extraction**
- Automatically extracts parameters from natural language queries
- Uses regex patterns to detect:
  - PO numbers (5-6 digits): "Generate report for PO 55269"
  - Order keys (format: `XX:123456789`): "Show details for order US:300000123456789"
  - Export formats: "Export to Excel" → `format=xlsx`
  - Workbook IDs (Base64): Detects long alphanumeric strings

### 2. **API Spec Defaults**
- Loads defaults from `api_spec_*.json` files
- Finance: `po_number=55269`, `format=pdf`, `report_path=/Custom/ROIC/ROIC_PO_REPORTS.xdo`
- Orders: `limit=10`
- Reports: `workbook_id=L3NoYXJlZC9SQ09FL0Fic2VuY2UgV29ya2Jvb2s`, `format=pdf`, `api_version=20210901`
- HR: No defaults needed (uses full query as prompt)
- General: No parameters required

### 3. **Exact Parent App Logic**
All agent execution functions match `AskMeChatBot.py` exactly:

#### Finance Agent (BI Publisher SOAP)
- SOAP envelope with PO number and format
- Parses `<reportBytes>` tag for Base64 PDF
- Returns: `PDF_DOWNLOAD:Finance:{base64_data}`

#### HR Agent (ORDS GenAI Module)
- Passes full query to `/query?prompt={query}` endpoint
- Handles array results (tabular data) with pagination (first 10 of N)
- Handles object results with fallback fields: `query_result`, `response`, `reply`, `answer`

#### Orders Agent (Fusion SCM REST)
- **Detail mode**: When order key detected → `/salesOrdersForOrderHub/{order_key}` with line items
- **List mode**: When no order key → `/salesOrdersForOrderHub?limit=10` sorted by LastUpdateDate
- Pagination hint: "💡 Showing first 10 orders. Use specific Order ID for details."

#### Reports Agent (OAC Workbook Export)
- POST to `/api/{version}/catalog/workbooks/{id}/exports` with canvas IDs and format
- Waits 30 seconds for export job completion
- Retries download 3 times with 10s intervals
- Returns: `REPORT_DOWNLOAD:Reports:{format}:{base64_data}`

#### General Agent (Dual-Mode Intelligence)
- Help/capabilities keywords → Info message
- Database queries → ORDS NL2SQL via `/query` endpoint
- Knowledge questions → Would use OCI Gen AI Inference (not implemented in interactive version yet)

## Usage Examples

### Finance Queries
```
"Generate purchase order report for PO 55269"
→ Extracts: po_number=55269, format=pdf (default)

"Show PO 12345 in Excel format"
→ Extracts: po_number=12345, format=xls
```

### HR Queries
```
"What is the work from home policy?"
→ Passes full query to ORDS: prompt="What is the work from home policy?"

"Tell me about employee benefits"
→ Passes full query to ORDS: prompt="Tell me about employee benefits"
```

### Orders Queries
```
"List recent orders"
→ No order key detected → List mode with limit=10

"Show details for order US:300000123456789"
→ Extracts: order_key="US:300000123456789" → Detail mode

"Get last 20 orders"
→ Extracts: limit=20 → List mode
```

### Reports Queries
```
"Export workbook to PDF"
→ Uses default workbook_id, format=pdf

"Export analytics to Excel"
→ Uses default workbook_id, format=xlsx

"Export workbook {Base64_ID} as PNG"
→ Extracts: workbook_id={Base64_ID}, format=png
```

### General Queries
```
"What can you do?"
→ Shows capabilities message

"Help"
→ Shows help message with available agents

"List all customers"
→ Calls ORDS NL2SQL for database query
```

## Configuration

### Required Files
1. **config.properties** - Backend API endpoints and credentials
   ```properties
   finance_agent_url=http://...
   finance_agent_username=...
   finance_agent_password=...
   # Similar for hr, orders, reports, general
   genai_intent_mode=force  # or auto, off
   use_mock_responses=false
   ```

2. **api_spec_*.json** - OpenAPI 3.0 specs with server variables
   - `api_spec_finance.json` - BI Publisher SOAP
   - `api_spec_hr.json` - ORDS GenAI Module
   - `api_spec_orders.json` - Fusion SCM REST
   - `api_spec_reports.json` - OAC Workbook Export
   - `api_spec_general.json` - ORDS GenAI Module

3. **.env** - OCI credentials (optional if GenAI disabled)
   ```dotenv
   OCI_USER_OCID=ocid1.user.oc1...
   OCI_TENANCY_OCID=ocid1.tenancy.oc1...
   OCI_FINGERPRINT=...
   OCI_REGION=us-ashburn-1
   OCI_KEY_FILE=oci_api_key.pem
   ```

## Running Locally

```powershell
# Install dependencies
.\.venv\Scripts\python.exe -m pip install flask requests python-dotenv oci

# Run the app
.\.venv\Scripts\python.exe .\AskMeChatBot_Interactive.py

# Access at: http://localhost:5000
```

## Mock Response Mode
For testing without real APIs:
```properties
# In config.properties
use_mock_responses=true
```
All agents return hardcoded mock data.

## Download Handling
Large files (PDFs, reports) stored server-side in `download_storage` dictionary:
- Avoids cookie size limits (4KB max)
- Unique UUID per download
- Served via `/download/{id}` endpoint
- Proper MIME types for each format

## Differences from Parent App

| Feature | AskMeChatBot.py | AskMeChatBot_Interactive.py |
|---------|----------------|----------------------------|
| Parameter Collection | Manual/implicit | **Dynamic extraction from query** |
| Intent Detection | Hybrid (keyword + GenAI) | **Same** |
| API Defaults | Hardcoded | **Loaded from api_spec_*.json** |
| Response Handling | Same | **Same** |
| General Agent NL2SQL | ✅ Database keyword detection | ⚠️ ORDS call only (no keyword routing yet) |
| MCP Servers | ❌ No | ❌ No |
| UI | Basic chat | **Enhanced with parameter forms** |

## Next Steps
1. Test all agents with real backend APIs
2. Add General Agent dual-mode routing (database keywords vs knowledge)
3. Add OCI Gen AI Inference for General Agent knowledge questions
4. Improve parameter extraction patterns (more regex cases)
5. Add validation for extracted parameters (format checks)
6. Add user feedback for parameter extraction ("I detected PO 55269, is this correct?")

## Logging
All operations logged to `askme_interactive.log`:
- Intent detection results
- Parameter extraction
- API calls and responses
- Error handling

Check logs with:
```powershell
Get-Content .\askme_interactive.log -Tail 50
```

## Error Handling
Graceful degradation at all levels:
- OCI Gen AI unavailable → Fallback to keyword intent detection
- API timeout → User-friendly message with retry suggestion
- Authentication failure → Clear credential verification message
- Missing parameters → Uses defaults from API specs
- Invalid response → Logged internally, generic user message
