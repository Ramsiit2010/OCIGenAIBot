# OCI Gen AI Multi-Agent Chat Bot - Implementation Guide

## Overview

This guide details the architecture, routing logic, advisor integrations, configuration, Gen AI intent detection, server-side download storage, pagination, and extensibility for the multi-advisor Flask chat bot.

---

## 1. Architecture & Project Structure

```
OCI_Bot/
├── AskMeChatBot.py          # Main Flask application
├── config.properties        # Configuration for endpoints, credentials, and runtime toggles
├── requirements.txt         # Python dependencies
├── .env                     # OCI credentials for Gen AI (not committed)
├── README.md                # User documentation
├── IMPLEMENTATION_GUIDE.md  # Implementation guide
├── api_spec_*.json          # API specifications for each advisor
└── wallet/                  # Oracle Wallet files (if needed)
```

---

## 2. Advisors & Integrations

- **General & HR**: Oracle APEX/ORDS GenAI Module (GET with prompt)
- **Finance**: Oracle Fusion BI Publisher SOAP (ExternalReportWSSService, returns base64 PDF)
- **Orders**: Oracle Fusion Cloud SCM REST (Sales Orders list/detail)
- **Reports**: Oracle Analytics Cloud Workbook Export (OAC, 30s wait + download retries)

Each advisor has a dedicated function in `AskMeChatBot.py` and can be extended with new endpoints or logic.

---

## 3. Intent Routing Logic

- **OCI Gen AI (Chicago region)**: If enabled and available, the app uses Cohere Command R Plus via OCI Generative AI Inference to classify the user prompt and select a single advisor.
- **Keyword-based fallback**: If Gen AI is disabled, unavailable, or inconclusive, the app uses keyword matching to route to one or more advisors.
- **Configurable mode**: Controlled by `genai_intent_mode` in `config.properties` (`auto`, `force`, `off`).

**Key function:** `process_user_query(prompt)`

---

## 4. Server-Side Download Storage

- Large files (PDFs, reports) are stored in a server-side dictionary (`download_storage`) keyed by UUID.
- Download endpoints (`/download_pdf/<id>`, `/download_report/<id>`) serve files by UUID, avoiding session cookie size limits and allowing retryable downloads.
- Download markers (e.g., `PDF_DOWNLOAD:Finance:<base64>`) are intercepted and replaced with download links in the UI.

---

## 5. Pagination & List Formatting

- Orders and array responses are capped to 10 items per advisor reply.
- The UI and API responses include a hint (e.g., "showing 10 of N") when more items are available.
- True pagination (next/prev) is not yet implemented but can be added by tracking paging tokens or offsets.

---

## 6. Configuration & Environment

- `config.properties`: Controls endpoints, credentials, mock/API mode, timeouts, retries, and Gen AI routing mode.
- `.env`: Stores OCI credentials for Gen AI (not committed).
- `requirements.txt`: Includes Flask, requests, oci, python-dotenv, etc.

---

## 7. Logging & Debugging

- Logs to both console and `app.log` (INFO level).
- Key log lines:
  - `OCI Gen AI client initialized successfully for Chicago region`
  - `Gen AI intent routing mode: auto|force|off`
  - `Attempting OCI Gen AI intent detection...` and `Gen AI detection result: <intent>`
  - `Using keyword-based routing (Gen AI not available or failed)`
- For debugging intent detection, add or check logs in `process_user_query` and `detect_intent_with_genai`.

---

## 8. Extending the System

- **Add a new advisor:**
  1. Add keywords to `advisor_keywords` in `process_user_query`.
  2. Create a new function (e.g., `get_new_advisor_advice`).
  3. Add config and API spec as needed.
  4. Update the UI template for new sample prompts.
- **Change routing:**
  - Adjust logic in `process_user_query` to support multi-intent or more advanced classification.
- **Add pagination:**
  - Track paging tokens or offsets in advisor functions and UI.

---

## 9. Security & Best Practices

- Never commit `.env` or real credentials.
- Use Basic Auth for API calls where required.
- Validate and sanitize all user input.
- Use HTTPS endpoints for all integrations.
- Consider adding rate limiting and user authentication for production.

---

## 10. Future Improvements

- True multi-intent routing (route to multiple advisors based on Gen AI output)
- Real pagination (next/prev page support)
- Conversation history and user authentication
- Advanced analytics and monitoring
- Enhanced error handling and retry logic

---

_Last updated: November 10, 2025_
