# General Agent Architecture - Dual-Mode Intelligence

## Overview

The General Agent in both **AskMeChatBot.py** and **RCOEGenAIAgents.py** uses a sophisticated dual-mode routing system that intelligently handles two distinct types of queries:

1. **Database/Data Queries** → ORDS NL2SQL
2. **General Knowledge Questions** → OCI Gen AI Inference

---

## Architecture Diagram

```
User Query
    │
    ▼
┌───────────────────────────────────┐
│   Intent Detection Layer          │
│   (OCI Gen AI: "general")         │
└───────────────────────────────────┘
    │
    ▼
┌───────────────────────────────────┐
│   Keyword Analysis                │
│   (Database-style keywords?)      │
└───────────────────────────────────┘
    │
    ├─ Database Keywords Detected
    │  (list, show, get, count, etc.)
    │       │
    │       ▼
    │  ┌──────────────────────────┐
    │  │  ORDS GenAI Module       │
    │  │  (NL2SQL Translation)    │
    │  └──────────────────────────┘
    │       │
    │       ▼
    │  SQL Execution → Structured Data
    │  (Paginated if >10 records)
    │
    └─ No Database Keywords
       (knowledge, explanation, etc.)
            │
            ▼
       ┌──────────────────────────┐
       │  OCI Gen AI Inference    │
       │  (cohere.command-plus)   │
       └──────────────────────────┘
            │
            ▼
       Educational Response
       (Explanations, definitions)
```

---

## Database Keyword Detection

The system detects database-style queries using this keyword set:

```python
database_keywords = [
    'list', 'show', 'get', 'find', 'search', 'query', 'select', 
    'count', 'sum', 'average', 'table', 'database', 'record', 
    'data', 'customer', 'employee', 'product', 'item', 
    'all', 'total', 'how many', 'sql', 'translate'
]
```

**Detection Logic:**
```python
is_database_query = any(keyword in query.lower() for keyword in database_keywords)
```

---

## Mode 1: ORDS NL2SQL (Database Queries)

### Purpose
Translate natural language questions into SQL queries and execute them against configured databases.

### Endpoint
```
https://your-ords-endpoint/ords/select_ai_user/genai_module/query
```

### Authentication
- **Optional**: No credentials required if endpoint is publicly accessible
- **Basic Auth**: `SELECT_AI_USER` / `Oracle##2025AI` (if configured)

### Request Format
```http
GET /ords/select_ai_user/genai_module/query?prompt=List+all+customers
Accept: application/json
Authorization: Basic <base64-encoded-creds>  # Optional
```

### Response Handling
1. **Array Response** (list of records):
   ```python
   if isinstance(data, list) and len(data) > 0:
       top_items = data[:10]  # Limit to first 10
       formatted = [f"{idx}. {key1}: {val1}, {key2}: {val2}" for idx, item in enumerate(top_items, 1)]
       if len(data) > 10:
           result += "\n\n💡 Showing first 10 of {len(data)} records."
   ```

2. **Object Response** (single result or nested):
   ```python
   result = data.get('query_result', data.get('response', data.get('reply', data.get('answer'))))
   ```

### Sample Queries
- "List all customers"
- "Show employee count by department"
- "Find products with price > 100"
- "Count total orders this month"
- "Get customer details for ID 12345"

---

## Mode 2: OCI Gen AI Inference (Knowledge Questions)

### Purpose
Answer general knowledge, educational, or explanatory questions using OCI's large language model.

### Model
- **Model ID**: `cohere.command-plus-latest`
- **Region**: `us-ashburn-1` (default)
- **Temperature**: 0.7 (balanced creativity)
- **Max Tokens**: 500

### Configuration
```python
chat_request = CohereChatRequest(
    message=query,
    max_tokens=500,
    temperature=0.7,
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
answer = response.data.chat_response.text.strip()
```

### Sample Queries
- "What is cloud computing?"
- "Explain machine learning in simple terms"
- "How does blockchain work?"
- "Tell me about Oracle Database"
- "What are the benefits of microservices?"

---

## Fallback Chain

The system implements a robust fallback mechanism:

```
1. Try ORDS (if database query detected)
   ↓ [FAIL]
2. Try OCI Gen AI Inference
   ↓ [FAIL]
3. Try ORDS anyway (alternate route)
   ↓ [FAIL]
4. Keyword-based responses
   ↓ [FAIL]
5. Generic error message
```

### Keyword-Based Fallbacks

Built-in responses for common queries:

| Keyword | Response |
|---------|----------|
| `help` | "I am a General Agent that can assist you with Finance, HR, Orders, or Reports queries..." |
| `capabilities` | "I can help you with:\n• Financial queries...\n• HR policies...\n• Order management...\n• Analytics reports..." |
| `services` | "Our advisory system provides specialized assistance through dedicated agents..." |
| `what can you do` | "I can answer general questions, translate natural language to SQL for data queries..." |
| `nlp`, `nlp2sql` | "I support NL2SQL via the ORDS GenAI Module; ask things like 'List all customers'." |

---

## Implementation Differences

### AskMeChatBot.py (Hybrid App)

**Location:** `get_general_advice()` function (lines ~540-600)

**Routing Mode:** `auto` (keyword fallback enabled)

**Key Code:**
```python
def get_general_advice(query: str) -> str:
    # Detect database keywords
    database_keywords = ['list', 'show', 'get', ...]
    is_database_query = any(kw in query.lower() for kw in database_keywords)
    
    if is_database_query:
        # Try ORDS NL2SQL
        api_response = call_agent_api('general', query)
        if api_response:
            return api_response
    
    # Use OCI Gen AI for knowledge
    if genai_client:
        chat_request = CohereChatRequest(message=query, max_tokens=500, temperature=0.7, ...)
        response = genai_client.chat(chat_details)
        return response.data.chat_response.text.strip()
    
    # Fallback to keywords
    for keyword, response in keyword_responses.items():
        if keyword in query.lower():
            return response
```

### RCOEGenAIAgents.py (MCP Architecture)

**Location:** 
- `route_to_mcp_server()` in `RCOEGenAIAgents.py` (lines ~270-340)
- `GeneralMCPServer.handle_request()` in `mcp_servers/advisors.py` (lines ~20-120)

**Routing Mode:** `force` (pure Gen AI intent)

**Key Code:**
```python
# In RCOEGenAIAgents.py routing layer
if detected_intent == 'general':
    database_keywords = ['list', 'show', 'get', ...]
    is_database_query = any(k in prompt.lower() for k in database_keywords)
    
    if is_database_query:
        # Route to ORDS via General MCP Server
        response = server.handle_request(prompt)
    else:
        # Direct OCI Gen AI call
        if genai_client:
            chat_response = genai_client.chat(chat_details)
            response = chat_response.data.chat_response.text.strip()
        else:
            response = server.handle_request(prompt)  # Fallback to MCP
```

---

## Configuration

### config.properties

```properties
# General Agent (ORDS NL2SQL) - No credentials required if endpoint is public
general_agent_url=https://g741db48c41b919-atpdb.adb.ap-hyderabad-1.oraclecloudapps.com/ords/select_ai_user/genai_module/query
general_agent_username=
general_agent_password=

# OCI Gen AI Configuration (for intent detection + general knowledge)
genai_region=us-ashburn-1
genai_intent_mode=auto  # or 'force' for RCOE

# API Settings
use_mock_responses=false
api_timeout=30
```

### .env (OCI Gen AI Authentication)

```dotenv
# OCI Configuration for Gen AI
OCI_USER=ocid1.user.oc1..aaaaaaaaxxx
OCI_KEY_FILE=oci_api_key.pem
OCI_FINGERPRINT=77:7b:98:26:4d:b9:xxx
OCI_TENANCY=ocid1.tenancy.oc1..aaaaaaaaxxxs
OCI_REGION=ap-hyderabad-1
```

---

## OCI Functions Deployment

### func_askme.yaml

```yaml
schema_version: 20180708
name: askme-chatbot-fn
version: 0.0.1
runtime: python
memory: 1024
timeout: 120
config:
  agentEndpointId: <agent-endpoint-id>
  genaiIntentMode: auto
  genaiRegion: us-ashburn-1  # Updated from us-chicago-1
```

### func_rcoe.yaml

```yaml
schema_version: 20180708
name: rcoe-genai-agents-mcp-fn
version: 0.0.1
runtime: python
memory: 1024
timeout: 120
config:
  agentEndpointId: <agent-endpoint-id>
  genaiIntentMode: force
  genaiRegion: us-ashburn-1  # Updated from us-chicago-1
```

**Note:** Update `<agent-endpoint-id>` with your actual OCI Gen AI Agent Endpoint OCID before deployment.

---

## Testing Examples

### Test Database Queries (ORDS NL2SQL)

```bash
# Using AskMeChatBot
curl -X POST http://localhost:5000/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "List all customers with their email addresses"}'

# Using RCOEGenAIAgents
curl -X POST http://localhost:5000/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Show employee count by department"}'
```

**Expected Response:**
```
🎯 General Agent 🤖
────────────────────────────
1. Customer: John Doe, Email: john@example.com
2. Customer: Jane Smith, Email: jane@example.com
...
💡 Showing first 10 of 145 records.
```

### Test General Knowledge (OCI Gen AI)

```bash
curl -X POST http://localhost:5000/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is cloud computing?"}'
```

**Expected Response:**
```
🎯 General Agent 🤖
────────────────────────────
Cloud computing is a revolutionary technology that has transformed 
the way data is stored, accessed, and managed. It refers to the 
delivery of computing services, including servers, storage, databases, 
networking, software, analytics, and intelligence, over the Internet 
("the cloud") to offer faster innovation, flexible resources, and 
economies of scale...
```

---

## Benefits

### For Database Queries (NL2SQL)
✅ Natural language interface to structured data  
✅ No SQL knowledge required for end users  
✅ Consistent data format (JSON/structured)  
✅ Direct database access via ORDS  
✅ Pagination for large result sets  

### For General Knowledge
✅ Accurate, contextual responses  
✅ Educational and explanatory content  
✅ Latest model capabilities (cohere.command-plus)  
✅ No external data needed  
✅ Fast response times  

### Combined System
✅ Single conversational interface  
✅ Intelligent routing based on query type  
✅ Robust fallback mechanisms  
✅ Graceful degradation when APIs unavailable  
✅ Keyword-based safety net  

---

## Troubleshooting

### Issue: ORDS returns 401 Unauthorized
**Solution:** Check if endpoint requires authentication; update credentials in `config.properties`

### Issue: Gen AI returns generic/unhelpful answers
**Solution:** Refine prompt or adjust temperature; consider adding system prompt

### Issue: Database queries return "No data"
**Solution:** Verify ORDS endpoint connectivity; check database has data; review SQL generation

### Issue: Both modes fail
**Solution:** Check fallback to keyword responses; ensure `general_keyword_responses` dict is populated

---

## Future Enhancements

- **Prompt Engineering**: Add system prompts to improve Gen AI responses
- **Context Memory**: Implement session-based context for multi-turn conversations
- **Hybrid Responses**: Combine ORDS data with Gen AI explanations
- **Query Optimization**: Cache frequent NL2SQL translations
- **Admin Interface**: UI to view/manage keyword mappings and fallbacks

---

## Summary

The dual-mode General Agent architecture provides:

1. **Flexibility**: Handles both data queries and knowledge questions
2. **Intelligence**: Smart keyword detection and routing
3. **Reliability**: Multi-level fallback mechanisms
4. **User Experience**: Single interface for diverse query types
5. **Scalability**: Modular design for easy extension

Both AskMeChatBot and RCOEGenAIAgents implement this pattern, with minor variations based on their architectural styles (hybrid vs MCP).
