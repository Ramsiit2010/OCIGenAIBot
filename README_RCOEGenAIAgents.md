# RCOE Gen AI Agents - MCP Architecture

## Overview

**RCOEGenAIAgents** is an intelligent, enterprise-grade multi-advisor system built on **Model Context Protocol (MCP)** architecture with **pure OCI Generative AI intent-based routing**. Unlike traditional keyword-based routing, this application uses Oracle Cloud Infrastructure's Generative AI service to intelligently understand user intent and route queries to specialized advisory agents.

## 🌟 Key Features

### 1. **Pure Gen AI Intent Detection**
- No keyword-based fallbacks
- Leverages OCI Gen AI (`cohere.command-plus-latest`) for intelligent query classification
- Understands natural language intent across 5 advisor domains

### 2. **MCP Server Architecture**
- Each advisor is implemented as an independent MCP server
- Standardized interface for easy extensibility
- Modular, maintainable, and testable design

### 3. **5 Specialized Advisors**

| Advisor | Domain | Backend Integration |
|---------|--------|---------------------|
| **General Agent 🤖** | General inquiries, help, capabilities | ORDS GenAI Module |
| **Finance Advisor 💰** | Revenue, budgets, financial reports | BI Publisher SOAP API |
| **HR Advisor 👥** | Policies, benefits, employee matters | ORDS GenAI Module |
| **Orders Advisor 📦** | Sales orders, inventory, delivery | Oracle Fusion SCM REST API |
| **Reports Advisor 📊** | Analytics, dashboards, exports | Oracle Analytics Cloud (OAC) API |

### 4. **Enterprise Integrations**
- **Oracle APEX/ORDS**: GenAI Module for General and HR queries
- **BI Publisher**: SOAP API for financial report generation (PDF)
- **Fusion SCM**: REST API for sales order management
- **Oracle Analytics Cloud**: Workbook export API (PDF/PNG/XLSX/CSV)

### 5. **Production-Ready Features**
- Server-side download storage for large files
- Configurable API timeouts and retry logic
- Comprehensive logging with advisor-specific prefixes
- Mock response mode for testing
- Health check endpoint (`/mcp/servers`)

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    RCOEGenAIAgents.py                       │
│                     (Flask Application)                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  OCI Gen AI     │
                    │  Intent Detector│
                    │  (Chicago-1)    │
                    └─────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌──────────────┐      ┌──────────────┐     ┌──────────────┐
│  General MCP │      │ Finance MCP  │ ... │ Reports MCP  │
│    Server    │      │   Server     │     │   Server     │
└──────────────┘      └──────────────┘     └──────────────┘
        │                     │                     │
        ▼                     ▼                     ▼
┌──────────────┐      ┌──────────────┐     ┌──────────────┐
│  ORDS GenAI  │      │ BI Publisher │     │     OAC      │
│    Module    │      │  SOAP API    │     │  Export API  │
└──────────────┘      └──────────────┘     └──────────────┘
```

## 🚀 Quick Start

### Prerequisites

1. **Python 3.8+**
2. **OCI SDK**: `pip install oci`
3. **Flask**: `pip install flask python-dotenv requests`
4. **OCI Account** with Gen AI access in `us-chicago-1` region
5. **Backend API Access**:
   - Oracle APEX/ORDS endpoints
   - BI Publisher instance
   - Oracle Fusion SCM instance
   - Oracle Analytics Cloud instance

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/Ramsiit2010/OCIGenAIBot.git
   cd OCIGenAIBot
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables** (`.env` file)
   ```properties
   OCI_USER=ocid1.user.oc1..aaaaaaaa...
   OCI_FINGERPRINT=aa:bb:cc:dd:ee:ff:...
   OCI_TENANCY=ocid1.tenancy.oc1..aaaaaaaa...
   OCI_KEY_FILE=~/.oci/oci_api_key.pem
   ```

4. **Configure application** (`config.properties`)
   ```properties
   genai_region=us-chicago-1
   use_mock_responses=false
   api_timeout=30
   
   # Configure each advisor's API endpoints and credentials
   general_agent_url=https://your-ords-endpoint/genai_module/query
   finance_agent_url=https://your-bi-publisher/xmlpserver/services/...
   # ... (see config.properties for all settings)
   ```

### Running the Application

```bash
python RCOEGenAIAgents.py
```

The application will start on **http://localhost:5001**

## 📖 Usage

### Web Interface

1. Navigate to `http://localhost:5001`
2. Use the sample buttons or type your query
3. Gen AI automatically detects intent and routes to the appropriate advisor

### Sample Queries

| Query | Detected Intent | Response |
|-------|----------------|----------|
| "Show all customers" | General | List of customers from ORDS |
| "Show me finance reports" | Finance | PDF financial report download |
| "List employee details" | HR | Employee data from ORDS |
| "Show sales orders" | Orders | Recent orders from Fusion SCM |
| "Show analytics dashboards" | Reports | OAC workbook export |

### API Endpoints

#### `POST /chat`
Process user query with Gen AI routing
```json
{
  "prompt": "Show me the latest financial reports"
}
```

**Response:**
```json
{
  "reply": "🎯 Finance Advisor 💰\n────────────────\n📄 Your report is ready!",
  "has_pdf": true,
  "download_url": "/download_pdf/uuid-here"
}
```

#### `GET /mcp/servers`
List all registered MCP servers
```json
{
  "total": 5,
  "servers": [
    {
      "name": "General Agent",
      "status": "registered",
      "registered_at": "2025-11-11T10:30:00"
    },
    // ... other servers
  ],
  "genai_enabled": true,
  "genai_region": "us-chicago-1"
}
```

## 🔧 Configuration

### Gen AI Settings

```properties
# config.properties
genai_region=us-chicago-1          # OCI Gen AI region
genai_intent_mode=force            # force|auto|off
```

The application uses `cohere.command-plus-latest` model by default (hardcoded for stability).

### Advisor Configuration

Each advisor requires:
- API endpoint URL
- Authentication credentials (username/password or API key)
- Timeout settings

Example for Finance Advisor:
```properties
finance_agent_url=https://your-bi-publisher-endpoint/...
finance_agent_username=your_username
finance_agent_password=your_password
```

### Mock Response Mode

For testing without backend APIs:
```properties
use_mock_responses=true
```

## 🧪 Testing

### Test MCP Server Registration

Check server status:
```bash
curl http://localhost:5001/mcp/servers
```

### Test Intent Detection

Send test queries and verify routing:
```bash
curl -X POST http://localhost:5001/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Show me financial reports"}'
```

Expected: Routes to Finance Advisor

### Test Each Advisor

Use the sample buttons in the web UI to test all 5 advisors.

## 📊 Logging

Logs are written to `rcoe_genai_agents.log` with the following format:

```
2025-11-11 10:30:15 - INFO - ✓ OCI Gen AI client initialized for us-chicago-1
2025-11-11 10:30:15 - INFO - ✓ 5 MCP servers registered: ['general', 'finance', 'hr', 'orders', 'reports']
2025-11-11 10:30:20 - INFO - [Routing] Processing query: Show me finance reports
2025-11-11 10:30:21 - INFO - [Intent Detection] Calling Gen AI with model: cohere.command-plus-latest
2025-11-11 10:30:22 - INFO - ✓ Gen AI detected intent: 'finance'
2025-11-11 10:30:22 - INFO - [Routing] Routing to MCP server: Finance Advisor
2025-11-11 10:30:22 - INFO - [Finance MCP] Processing request
```

Each MCP server logs with its own prefix for easy debugging.

## 🔒 Security

1. **Credentials**: Store in `.env` file (not in version control)
2. **HTTPS**: Use HTTPS in production for all API endpoints
3. **API Keys**: Rotate regularly and use OCI Vault in production
4. **Download Storage**: Server-side storage is in-memory; implement cleanup for production

## 🆚 Comparison: MCP vs Hybrid App

| Feature | AskMeChatBot.py (Hybrid) | RCOEGenAIAgents.py (MCP) |
|---------|--------------------------|--------------------------|
| Architecture | Monolithic functions | MCP server classes |
| Routing | Keyword + Gen AI fallback | Pure Gen AI only |
| Extensibility | Manual function addition | Add new MCP server class |
| Testing | Test entire app | Test each server independently |
| Port | 5000 | 5001 |
| Logging | Mixed advisor logs | Server-specific prefixes |
| Code Organization | ~1100 lines, one file | Modular: base + advisors |

## 🛠️ Troubleshooting

### Gen AI Intent Detection Fails

**Symptom**: All queries route to General advisor

**Solutions**:
1. Check OCI credentials in `.env`
2. Verify `genai_region=us-chicago-1` in `config.properties`
3. Ensure OCI tenancy has access to Gen AI in Chicago region
4. Check logs for API errors

### MCP Server Not Registering

**Symptom**: Less than 5 servers in `/mcp/servers` response

**Solutions**:
1. Check API endpoint configuration in `config.properties`
2. Verify credentials for that advisor
3. Check logs for registration errors
4. Try `use_mock_responses=true` to isolate API issues

### Download Not Working

**Symptom**: PDF/Report download fails

**Solutions**:
1. Check download_storage size (memory limit)
2. Verify base64 encoding in API response
3. Check browser console for download errors

## 📚 API Specifications

API specs are defined in JSON files:
- `api_spec_general.json` - ORDS GenAI Module spec
- `api_spec_finance.json` - BI Publisher SOAP spec
- `api_spec_hr.json` - ORDS GenAI Module spec
- `api_spec_orders.json` - Fusion SCM REST spec
- `api_spec_reports.json` - OAC Export API spec

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Add new MCP server in `mcp_servers/advisors.py`
4. Register in `RCOEGenAIAgents.py`
5. Update intent classification prompt
6. Submit pull request

## 📄 License

[Your License Here]

## 👥 Authors

- **Ramsiit2010** - Initial work

## 🙏 Acknowledgments

- Oracle Cloud Infrastructure Gen AI team
- Flask framework
- Model Context Protocol community

## 📞 Support

For issues and questions:
- GitHub Issues: https://github.com/Ramsiit2010/OCIGenAIBot/issues
- Email: [Your Email]

---

**Built with ❤️ using OCI Gen AI and Model Context Protocol**
