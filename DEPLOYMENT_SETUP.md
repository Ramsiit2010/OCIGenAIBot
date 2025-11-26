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
```

### 3. Create OCI Functions Application

**Using OCI Console:**
1. Navigate to Developer Services → Functions
2. Create Application:
   - Name: `askme-chatbot-app` or `rcoe-genai-agents-app`
   - VCN: Select your VCN
   - Subnet: Select public or private subnet
3. Note the Application OCID

**Using OCI CLI:**
```bash
oci fn application create \
  --compartment-id <compartment-ocid> \
  --display-name askme-chatbot-app \
  --subnet-ids '["<subnet-ocid>"]'
```

### 4. Create OCI Gen AI Agent Endpoint

1. Navigate to AI Services → Generative AI Agents
2. Create Agent:
   - Model: cohere.command-plus-latest
   - Region: us-ashburn-1 (default)
3. Deploy and note the `agentEndpointId`

### 5. Update Function Configuration

**Edit `func_askme.yaml` or `func_rcoe.yaml`:**
```yaml
config:
  agentEndpointId: ocid1.genaiagentendpoint.oc1.us-ashburn-1.amaaa...
  genaiIntentMode: auto  # or force
  genaiRegion: us-ashburn-1
```

### 6. Deploy Function

**For AskMeChatBot:**
```bash
cd OCIGenAIBot
fn deploy --app askme-chatbot-app --local func_askme.py
```

**For RCOEGenAIAgents:**
```bash
fn deploy --app rcoe-genai-agents-app --local func_rcoe.py
```

### 7. Test Function

```bash
echo '{"sessionId":"test-001","prompt":"Show me finance reports"}' | \
  fn invoke askme-chatbot-app askme-chatbot-fn
```

### 8. Configure API Gateway (Optional)

Create API Gateway to expose function as REST endpoint:
```bash
# Create deployment with POST /chat route
# Point to Functions backend
```

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
