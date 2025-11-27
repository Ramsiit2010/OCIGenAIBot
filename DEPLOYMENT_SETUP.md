# Deployment Setup Guide

This document provides comprehensive setup instructions for all deployment scenarios.

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Local Development Setup](#local-development-setup)
3. [OCI Functions Deployment](#oci-functions-deployment)
4. [Google Colab Deployment](#google-colab-deployment)
5. [Environment Configuration](#environment-configuration)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements
- **Python**: 3.11 or 3.12
- **Git**: Latest version
- **OCI CLI**: For OCI Functions deployment
- **Docker**: For local OCI Functions testing

### Required Accounts
- Oracle Cloud Infrastructure (OCI) account
- GitHub account (for Colab deployments)
- Ngrok account (free tier sufficient)

---

## Local Development Setup

### 1. Clone Repository
```bash
git clone https://github.com/Ramsiit2010/OCIGenAIBot.git
cd OCIGenAIBot
```

### 2. Create Virtual Environment

**Windows:**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Linux/Mac:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Edit `.env` with your credentials:
```dotenv
# OCI API Authentication
OCI_USER_OCID=ocid1.user.oc1..aaaaaaa...
OCI_TENANCY_OCID=ocid1.tenancy.oc1..aaaaaaa...
OCI_FINGERPRINT=ab:cd:ef:12:34:56...
OCI_REGION=us-ashburn-1
OCI_KEY_FILE=oci_api_key.pem

# Gen AI Configuration
GENAI_REGION=us-ashburn-1
GENAI_MODEL=cohere.command-plus-latest
GENAI_INTENT_MODE=force
```

### 5. Add OCI API Key

Place your `oci_api_key.pem` file in the project root directory.

### 6. Update config.properties

Edit backend service credentials in `config.properties`:
```properties
# Finance Agent (BI Publisher)
finance_agent_username=your_username
finance_agent_password=your_password

# Orders Agent (Fusion SCM)
orders_agent_username=your_username
orders_agent_password=your_password

# Reports Agent (OAC)
reports_agent_username=your_username
reports_agent_password=your_password
```

### 7. Run Applications

**AskMeChatBot (Hybrid Intent):**
```bash
python AskMeChatBot.py
```

**RCOEGenAIAgents (MCP Architecture):**
```bash
python RCOEGenAIAgents.py
```

Access at: `http://localhost:5000`

---

## OCI Functions Deployment

### 1. Install OCI CLI and Fn CLI

**OCI CLI:**
```bash
bash -c "$(curl -L https://raw.githubusercontent.com/oracle/oci-cli/master/scripts/install/install.sh)"
```

**Fn CLI:**
```bash
# Linux/Mac
curl -LSs https://raw.githubusercontent.com/fnproject/cli/master/install | sh

# Windows (WSL)
wsl --install
# Then run Linux commands inside WSL
```

### 2. Configure OCI CLI
```bash
oci setup config
# Follow prompts to configure:
# - User OCID
# - Tenancy OCID
# - Region
# - API Key
```

### 3. Create OCI Gen AI Agent Endpoint

1. **Navigate to OCI Console** → AI Services → Generative AI Agents

2. **Create Agent**:
   - Name: `multi-advisor-agent` or similar
   - Model: `cohere.command-plus-latest`
   - Region: `us-ashburn-1` (default, configurable)

3. **Deploy Agent** and copy the **Agent Endpoint OCID**:
   ```
   ocid1.genaiagentendpoint.oc1.us-ashburn-1.amaaaaaa...
   ```

### 4. Create Functions Application

**Option A: Using OCI Console**

1. Navigate to **Developer Services** → **Functions**
2. Click **Create Application**:
   - Name: `askme-chatbot-app` (or `rcoe-genai-agents-app`)
   - VCN: Select your VCN
   - Subnet: Select a subnet with internet access
3. Note the Application OCID

**Option B: Using OCI CLI**

```bash
# For AskMeChatBot
oci fn application create \
  --compartment-id ocid1.compartment.oc1..aaaaaa... \
  --display-name askme-chatbot-app \
  --subnet-ids '["ocid1.subnet.oc1.iad.aaaaaa..."]'

# For RCOEGenAIAgents
oci fn application create \
  --compartment-id ocid1.compartment.oc1..aaaaaa... \
  --display-name rcoe-genai-agents-app \
  --subnet-ids '["ocid1.subnet.oc1.iad.aaaaaa..."]'
```

### 5. Configure Fn CLI Context

```bash
# Get context info from Application page in OCI Console
fn list contexts

# Create new context
fn create context <region-key> --provider oracle

# Set compartment
fn update context oracle.compartment-id ocid1.compartment.oc1..aaaaaa...

# Set API URL
fn update context api-url https://functions.us-ashburn-1.oraclecloud.com

# Set registry (OCIR)
fn update context registry iad.ocir.io/<tenancy-namespace>/<repo-name>

# Use the context
fn use context <region-key>
```

### 6. Configure Docker for OCIR

```bash
# Login to OCIR (Oracle Cloud Infrastructure Registry)
docker login iad.ocir.io

# Username: <tenancy-namespace>/<oci-username>
# Password: <auth-token>
```

Generate auth token:
1. OCI Console → User Settings → Auth Tokens
2. Generate Token and copy it

### 7. Update Function Configuration Files

**Edit `func_askme.yaml`:**
```yaml
config:
  agentEndpointId: ocid1.genaiagentendpoint.oc1.us-ashburn-1.amaaaaaa...
  genaiIntentMode: auto
  genaiRegion: us-ashburn-1
```

**Edit `func_rcoe.yaml`:**
```yaml
config:
  agentEndpointId: ocid1.genaiagentendpoint.oc1.us-ashburn-1.amaaaaaa...
  genaiIntentMode: force
  genaiRegion: us-ashburn-1
```

### 8. Create Dynamic Group for Resource Principal

**OCI Console** → Identity → Dynamic Groups → Create

**Name:** `functions-dynamic-group`

**Matching Rule:**
```
ALL {resource.type = 'fnfunc', resource.compartment.id = 'ocid1.compartment.oc1..aaaaaa...'}
```

### 9. Create IAM Policy

**OCI Console** → Identity → Policies → Create

**Name:** `functions-genai-policy`

**Statements:**
```
Allow dynamic-group functions-dynamic-group to use generative-ai-agent-endpoint in compartment <compartment-name>
Allow dynamic-group functions-dynamic-group to manage generative-ai-agent-session in compartment <compartment-name>
Allow dynamic-group functions-dynamic-group to read secret-family in compartment <compartment-name>
```

### 10. Deploy Functions

**For AskMeChatBot:**
```bash
cd /path/to/OCIGenAIBot

# Initialize function (first time only)
fn init --runtime python askme-chatbot-fn
# Copy func_askme.py to askme-chatbot-fn/func.py
# Copy func_askme.yaml to askme-chatbot-fn/func.yaml

# Deploy
cd askme-chatbot-fn
fn deploy --app askme-chatbot-app
```

**Alternative: Direct deploy (if files structured correctly)**
```bash
# Ensure func_askme.py and func_askme.yaml are in a folder
mkdir -p fn-askme
cp func_askme.py fn-askme/func.py
cp func_askme.yaml fn-askme/func.yaml

cd fn-askme
fn deploy --app askme-chatbot-app --local
```

**For RCOEGenAIAgents:**
```bash
mkdir -p fn-rcoe
cp func_rcoe.py fn-rcoe/func.py
cp func_rcoe.yaml fn-rcoe/func.yaml

cd fn-rcoe
fn deploy --app rcoe-genai-agents-app --local
```

### 11. Test Function

```bash
# Get function OCID from OCI Console or CLI
fn inspect function askme-chatbot-app askme-chatbot-fn

# Invoke function
echo '{
  "sessionId": "test-session-001",
  "prompt": "Show me the latest finance reports"
}' | fn invoke askme-chatbot-app askme-chatbot-fn
```

**Expected Response:**
```json
{
  "message": "Here are the finance reports...",
  "sessionId": "test-session-001"
}
```

### 12. Configure API Gateway (Production)

**1. Create API Gateway**

**OCI Console** → Developer Services → API Gateway → Create

- Name: `genai-chatbot-gateway`
- Type: Public
- Compartment: Select compartment
- VCN & Subnet: Select

**2. Create API Deployment**

**Deployment Details:**
- Name: `chatbot-v1`
- Path Prefix: `/api/v1`

**Route 1: AskMeChatBot**
```
Path: /chat/askme
Methods: POST
Backend Type: Oracle Functions
Application: askme-chatbot-app
Function: askme-chatbot-fn
```

**Route 2: RCOEGenAIAgents**
```
Path: /chat/rcoe
Methods: POST
Backend Type: Oracle Functions
Application: rcoe-genai-agents-app
Function: rcoe-genai-agents-app-fn
```

**3. Test via API Gateway**

```bash
curl -X POST https://your-gateway-id.apigateway.us-ashburn-1.oci.customer-oci.com/api/v1/chat/askme \
  -H "Content-Type: application/json" \
  -d '{
    "sessionId": "web-session-001",
    "prompt": "What are the latest sales orders?"
  }'
```

### 13. Configuration Management (OCI Vault)

Store sensitive backend credentials in OCI Vault:

1. **Create Vault** → OCI Console → Security → Vault
2. **Create Secrets** for:
   - Finance credentials
   - Orders credentials
   - Reports credentials

3. **Update IAM Policy:**
```
Allow dynamic-group functions-dynamic-group to read secret-family in compartment <compartment-name>
```

4. **Modify Functions to Read Secrets:**
```python
import oci

signer = oci.auth.signers.get_resource_principals_signer()
secrets_client = oci.secrets.SecretsClient(config={}, signer=signer)

# Retrieve secret
secret_bundle = secrets_client.get_secret_bundle(
    secret_id="ocid1.vaultsecret.oc1.iad.amaaa..."
)
secret_value = base64.b64decode(secret_bundle.data.secret_bundle_content.content).decode()
```

### 14. Monitoring and Logging

**View Function Logs**

**OCI Console:**
1. Navigate to Functions → Applications → Your App → Function
2. Click **Logs** tab
3. View invocation logs in OCI Logging service

**Using CLI:**
```bash
# Stream logs
fn logs -f askme-chatbot-app askme-chatbot-fn
```

**Enable Metrics**

Functions automatically emit metrics to OCI Monitoring:
- Invocation count
- Execution duration
- Error count

**View in Console:**
OCI Console → Observability → Metrics Explorer

---

## Google Colab Deployment

### 1. Prepare Repository

Ensure sensitive files are NOT committed:
```bash
# Check git status
git status

# Should NOT see:
# - .env
# - oci_api_key.pem
# - *.pem files
```

### 2. Push to GitHub

```bash
git add .
git commit -m "Update deployment configuration"
git push origin main
```

### 3. Open Colab Notebook

**For AskMeChatBot:**
1. Go to: `https://colab.research.google.com/github/Ramsiit2010/OCIGenAIBot/blob/main/RCOE_OCIGenAIBot.ipynb`
2. Or upload `RCOE_OCIGenAIBot.ipynb` to Colab

**For RCOEGenAIAgents:**
1. Go to: `https://colab.research.google.com/github/Ramsiit2010/OCIGenAIBot/blob/main/Colab_Deploy_RCOE_GenAI_Apps.ipynb`
2. Or upload `Colab_Deploy_RCOE_GenAI_Apps.ipynb` to Colab

### 4. Run Notebook Cells

**Important:** Follow cells in order:
1. Install dependencies
2. Clone repository
3. **Upload `.env` and `oci_api_key.pem`** when prompted
4. Set ngrok authtoken
5. Start application
6. Access public URL

### 5. Access Application

After running all cells, you'll see:
```
🌍 Public URL: https://xxxx-xx-xx-xxx-xx.ngrok-free.app
```

Open this URL in your browser.

---

## Environment Configuration

### Virtual Environment Path Issue Fix

The current venv was created at `c:\Users\ramsi\OneDrive\Quick_Read\Explore\OCI_Bot\.venv` but project is now at `C:\Softwares\OCI_Bot\`. 

**To fix:**

1. **Option A: Recreate venv in current location**
   ```powershell
   # Remove old venv
   Remove-Item -Recurse -Force .venv
   
   # Create new venv
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   
   # Reinstall packages
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

2. **Option B: Use global Python (not recommended)**
   ```powershell
   # Just use system Python
   python -m pip install -r requirements.txt
   ```

### Global Python PATH Conflict

Your system has both Python 3.12.4 and Jython 2.7.4, causing pip conflicts.

**To fix:**
```powershell
# Always use full path to Python
C:\Users\ramsi\AppData\Local\Programs\Python\Python312\python.exe -m pip install <package>

# Or update PATH environment variable to prioritize Python 3.12
```

---

## Troubleshooting

### Issue: OCI SDK Import Error
```
cannot import name 'ChatDetails' from 'oci.generative_ai_inference.models'
```

**Solution:** Upgrade OCI SDK
```bash
pip install --upgrade oci
# Should install oci==2.164.0 or later
```

### Issue: Port 5000 Already in Use
```
Address already in use
```

**Solution:**
```powershell
# Find process using port 5000
netstat -ano | findstr :5000

# Kill the process
Stop-Process -Id <PID> -Force

# Or use different port
python AskMeChatBot.py --port 5001
```

### Issue: Function Deployment Fails

**Error:** `cannot pull image`

**Solution:**
```bash
# Verify Docker login
docker login iad.ocir.io

# Check OCIR path in func.yaml
# Should be: iad.ocir.io/<tenancy-namespace>/<repo-name>
```

### Issue: Resource Principal Auth Fails

**Error:** `Unable to get resource principal auth signer`

**Solution:**
1. Verify Dynamic Group includes your function
2. Check IAM policy grants required permissions
3. Ensure function is deployed in correct compartment

### Issue: Agent Endpoint Not Found

**Error:** `Agent endpoint not found`

**Solution:**
1. Verify `agentEndpointId` in `func.yaml` is correct
2. Ensure agent is deployed and active
3. Check IAM policy allows access to endpoint

### Issue: Function Timeout Errors

**Solution:**
Increase timeout in `func.yaml`:
```yaml
timeout: 300  # 5 minutes for longer operations
```

### Issue: oci_api_key.pem Not Found
```
[Errno 2] No such file or directory: 'oci_api_key.pem'
```

**Solution:**
1. Ensure `oci_api_key.pem` exists in project root
2. Check `.env` has `OCI_KEY_FILE=oci_api_key.pem`
3. Verify file permissions: `chmod 600 oci_api_key.pem` (Linux/Mac)

### Issue: Ngrok Tunnel Not Starting in Colab
```
ngrok error: authentication failed
```

**Solution:**
1. Get free authtoken from https://dashboard.ngrok.com/get-started/your-authtoken
2. Update in Colab notebook cell:
   ```python
   NGROK_AUTHTOKEN = "your-token-here"
   ```

### Issue: MCP Servers Not Registered
```
WARNING - OCI SDK not available - intent detection disabled
```

**Solution:**
1. Check OCI credentials in `.env`
2. Verify `oci_api_key.pem` is present
3. Confirm OCI Gen AI service is available in your region

---

## Best Practices

### Security
- ✅ Never commit `.env` or `*.pem` files to Git
- ✅ Use `.env.example` as template
- ✅ Rotate ngrok authtokens periodically
- ✅ Use OCI Vault for production secrets
- ✅ Enable Resource Principal auth for OCI Functions

### Development
- ✅ Use virtual environments for local dev
- ✅ Keep `requirements.txt` updated
- ✅ Test locally before deploying to OCI Functions
- ✅ Use descriptive commit messages
- ✅ Follow semantic versioning for releases

### Deployment
- ✅ Test in Colab before OCI Functions deployment
- ✅ Monitor function logs in OCI Console
- ✅ Set appropriate memory and timeout limits
- ✅ Use API Gateway for production REST endpoints
- ✅ Enable logging and tracing in OCI

---

## Support

For issues or questions:
- **Repository**: https://github.com/Ramsiit2010/OCIGenAIBot
- **OCI Docs**: https://docs.oracle.com/en-us/iaas/Content/functions/home.htm
- **Fn Project**: https://fnproject.io/
