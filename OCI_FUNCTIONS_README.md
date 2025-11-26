# OCI Functions Deployment Guide

## Overview

This guide covers deploying both applications as OCI Functions (serverless):
- **AskMeChatBot**: Hybrid intent routing with keyword fallback
- **RCOEGenAIAgents**: Pure Gen AI with MCP architecture

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    API Gateway (Optional)                    │
│                  https://your-api-gateway                     │
└───────────────────────────┬─────────────────────────────────┘
                            │
                ┌───────────┴───────────┐
                │                       │
        ┌───────▼──────┐       ┌───────▼──────┐
        │ AskMeChatBot │       │ RCOEGenAI    │
        │   Function   │       │   Agents     │
        │ (func_askme) │       │ (func_rcoe)  │
        └───────┬──────┘       └───────┬──────┘
                │                       │
                └───────────┬───────────┘
                            │
                ┌───────────▼───────────┐
                │  OCI Gen AI Agent     │
                │  Endpoint             │
                │  (Resource Principal) │
                └───────────┬───────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
   ┌────▼────┐       ┌─────▼─────┐      ┌─────▼─────┐
   │ BI Pub  │       │ Fusion    │      │    OAC    │
   │ SOAP    │       │ SCM REST  │      │ Workbooks │
   └─────────┘       └───────────┘      └───────────┘
```

## Prerequisites

### 1. OCI CLI Installation

**Linux/Mac:**
```bash
bash -c "$(curl -L https://raw.githubusercontent.com/oracle/oci-cli/master/scripts/install/install.sh)"
```

**Windows:**
```powershell
# Download and run installer from:
# https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm
```

### 2. Fn Project CLI

**Linux/Mac:**
```bash
curl -LSs https://raw.githubusercontent.com/fnproject/cli/master/install | sh
```

**Windows (via WSL or Docker Desktop):**
```bash
# Install WSL first
wsl --install

# Then inside WSL
curl -LSs https://raw.githubusercontent.com/fnproject/cli/master/install | sh
```

### 3. Docker Installation

Download from: https://www.docker.com/products/docker-desktop

### 4. OCI Configuration

```bash
oci setup config
# Follow prompts to configure:
# - User OCID
# - Tenancy OCID
# - Region
# - API Key
```

## Step-by-Step Deployment

### Step 1: Create OCI Gen AI Agent Endpoint

1. **Navigate to OCI Console** → AI Services → Generative AI Agents

2. **Create Agent**:
   - Name: `multi-advisor-agent` or similar
   - Model: `cohere.command-plus-latest`
   - Region: `us-ashburn-1` (default, configurable)

3. **Deploy Agent** and copy the **Agent Endpoint OCID**:
   ```
   ocid1.genaiagentendpoint.oc1.us-ashburn-1.amaaaaaa...
   ```

### Step 2: Create Functions Application

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

### Step 3: Configure Fn CLI Context

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

### Step 4: Configure Docker for OCIR

```bash
# Login to OCIR (Oracle Cloud Infrastructure Registry)
docker login iad.ocir.io

# Username: <tenancy-namespace>/<oci-username>
# Password: <auth-token>
```

Generate auth token:
1. OCI Console → User Settings → Auth Tokens
2. Generate Token and copy it

### Step 5: Update Function Configuration Files

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

### Step 6: Create Dynamic Group for Resource Principal

**OCI Console** → Identity → Dynamic Groups → Create

**Name:** `functions-dynamic-group`

**Matching Rule:**
```
ALL {resource.type = 'fnfunc', resource.compartment.id = 'ocid1.compartment.oc1..aaaaaa...'}
```

### Step 7: Create IAM Policy

**OCI Console** → Identity → Policies → Create

**Name:** `functions-genai-policy`

**Statements:**
```
Allow dynamic-group functions-dynamic-group to use generative-ai-agent-endpoint in compartment <compartment-name>
Allow dynamic-group functions-dynamic-group to manage generative-ai-agent-session in compartment <compartment-name>
Allow dynamic-group functions-dynamic-group to read secret-family in compartment <compartment-name>
```

### Step 8: Deploy Functions

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

### Step 9: Test Function

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

## API Gateway Integration (Production)

### 1. Create API Gateway

**OCI Console** → Developer Services → API Gateway → Create

- Name: `genai-chatbot-gateway`
- Type: Public
- Compartment: Select compartment
- VCN & Subnet: Select

### 2. Create API Deployment

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

### 3. Test via API Gateway

```bash
curl -X POST https://your-gateway-id.apigateway.us-ashburn-1.oci.customer-oci.com/api/v1/chat/askme \
  -H "Content-Type: application/json" \
  -d '{
    "sessionId": "web-session-001",
    "prompt": "What are the latest sales orders?"
  }'
```

## Configuration Management

### Using OCI Secrets (Recommended for Production)

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

## Monitoring and Logging

### View Function Logs

**OCI Console:**
1. Navigate to Functions → Applications → Your App → Function
2. Click **Logs** tab
3. View invocation logs in OCI Logging service

**Using CLI:**
```bash
# Stream logs
fn logs -f askme-chatbot-app askme-chatbot-fn
```

### Enable Metrics

Functions automatically emit metrics to OCI Monitoring:
- Invocation count
- Execution duration
- Error count

**View in Console:**
OCI Console → Observability → Metrics Explorer

## Troubleshooting

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

### Issue: Timeout Errors

**Solution:**
Increase timeout in `func.yaml`:
```yaml
timeout: 300  # 5 minutes for longer operations
```

## Cost Optimization

### Function Pricing

OCI Functions pricing (as of 2024):
- **Invocations**: $0.00000020 per request
- **Execution Time**: $0.00001417 per GB-second

### Cost Saving Tips

1. **Right-size Memory:**
   - Monitor actual memory usage
   - Adjust `memory` in func.yaml (256MB - 2048MB)

2. **Optimize Timeout:**
   - Set realistic timeouts
   - Avoid unnecessary waits

3. **Use Caching:**
   - Cache Gen AI responses for common queries
   - Implement Redis/OCI Cache

4. **Monitor Invocations:**
   - Set up budgets and alerts
   - Track usage patterns

## Production Checklist

- [ ] Resource Principal authentication configured
- [ ] Dynamic Group and IAM policies created
- [ ] Secrets stored in OCI Vault (not hardcoded)
- [ ] API Gateway deployed with rate limiting
- [ ] Logging enabled and monitored
- [ ] Metrics and alarms configured
- [ ] Function timeout and memory optimized
- [ ] Error handling implemented
- [ ] Health check endpoint added
- [ ] Documentation updated

## Additional Resources

- **OCI Functions Documentation**: https://docs.oracle.com/en-us/iaas/Content/Functions/home.htm
- **Fn Project**: https://fnproject.io/
- **OCI Gen AI Agents**: https://docs.oracle.com/en-us/iaas/Content/generative-ai-agents/home.htm
- **API Gateway**: https://docs.oracle.com/en-us/iaas/Content/APIGateway/home.htm
