"""
MCP Server implementations for each advisor
"""
import logging
import requests
import json
import re
import base64
import time
from datetime import datetime
from typing import Dict, Any
from requests.auth import HTTPBasicAuth
from .base_server import MCPServer

logger = logging.getLogger(__name__)


class GeneralMCPServer(MCPServer):
    """General Agent MCP Server - handles general inquiries and help"""
    
    def __init__(self, config: Dict[str, Any], api_spec: Dict[str, Any] = None):
        super().__init__(
            name="general",
            description="General inquiries, help, capabilities, services overview",
            config=config
        )
        self.api_spec = api_spec
        self.use_mock = config.get('use_mock_responses', 'true').lower() == 'true'
        self.url = config.get('general_agent_url')
        self.username = config.get('general_agent_username')
        self.password = config.get('general_agent_password')
        self.timeout = int(config.get('api_timeout', '30'))
    
    def handle_request(self, query: str) -> str:
        """Handle general queries via ORDS GenAI Module"""
        logger.info(f"[General MCP] Processing: {query}")
        
        if self.use_mock or not self.url:
            logger.info("[General MCP] Using mock response")
            return "I am a General Agent that can assist you with Finance, HR, Orders, or Reports queries. I can route your questions to specialized advisors or provide general information."
        
        try:
            params = {"prompt": query}
            headers = {"Accept": "application/json"}
            auth = HTTPBasicAuth(self.username, self.password) if self.username else None
            
            logger.info(f"[General MCP] Calling ORDS API: {self.url}")
            resp = requests.get(self.url, params=params, headers=headers, auth=auth, timeout=self.timeout)
            
            if resp.status_code == 200:
                data = resp.json()
                result = data.get('query_result', data.get('response', data.get('reply', data.get('answer'))))
                if result:
                    logger.info("[General MCP] API call successful")
                    return result
            
            logger.warning(f"[General MCP] API returned {resp.status_code}")
            return "General agent API unavailable. Please try again."
        except Exception as e:
            logger.error(f"[General MCP] Error: {e}")
            return f"General agent error: {str(e)}"


class FinanceMCPServer(MCPServer):
    """Finance Advisor MCP Server - handles BI Publisher SOAP reports"""
    
    def __init__(self, config: Dict[str, Any], api_spec: Dict[str, Any] = None):
        super().__init__(
            name="finance",
            description="Revenue, budget, expenses, costs, financial reports, profit/loss",
            config=config
        )
        self.api_spec = api_spec
        self.use_mock = config.get('use_mock_responses', 'true').lower() == 'true'
        self.url = config.get('finance_agent_url')
        self.username = config.get('finance_agent_username')
        self.password = config.get('finance_agent_password')
        self.timeout = int(config.get('api_timeout', '30'))
    
    def handle_request(self, query: str) -> str:
        """Handle finance queries via BI Publisher SOAP"""
        logger.info(f"[Finance MCP] Processing: {query}")
        
        if self.use_mock:
            logger.info("[Finance MCP] Using mock response")
            return "Based on our financial analysis, the Q3 revenue shows a 15% increase YoY with strong performance in APAC region."
        
        if not self.url or not self.username or not self.password:
            logger.warning("[Finance MCP] API not configured")
            return "Finance report API not configured."
        
        try:
            soap_body = '''<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" xmlns:pub="http://xmlns.oracle.com/oxp/service/PublicReportService">
   <soap:Header/>
   <soap:Body>
      <pub:runReport>
         <pub:reportRequest>
            <pub:attributeFormat>pdf</pub:attributeFormat>
            <pub:parameterNameValues>
               <pub:item>
                  <pub:name>P_PO_NUM</pub:name>
                  <pub:values>
                     <pub:item>55269</pub:item>
                  </pub:values>
               </pub:item>
            </pub:parameterNameValues>
            <pub:reportAbsolutePath>/Custom/ROIC/ROIC_PO_REPORTS.xdo</pub:reportAbsolutePath>
            <pub:sizeOfDataChunkDownload>-1</pub:sizeOfDataChunkDownload>
         </pub:reportRequest>
         <pub:appParams></pub:appParams>
      </pub:runReport>
   </soap:Body>
</soap:Envelope>'''
            
            headers = {
                "Content-Type": "application/soap+xml; charset=UTF-8",
                "SOAPAction": ""
            }
            
            logger.info(f"[Finance MCP] Calling BI Publisher SOAP: {self.url}")
            auth = HTTPBasicAuth(self.username, self.password)
            resp = requests.post(self.url, data=soap_body, headers=headers, auth=auth, timeout=self.timeout, verify=True)
            
            if resp.status_code == 200:
                match = re.search(r'<[^:]+:reportBytes>([^<]+)</[^:]+:reportBytes>', resp.text)
                if match:
                    pdf_b64 = match.group(1).strip()
                    logger.info(f"[Finance MCP] PDF generated ({len(pdf_b64)} chars)")
                    return f"PDF_DOWNLOAD:Finance:{pdf_b64}"
                else:
                    return "Report generated but PDF data not found."
            elif resp.status_code == 401:
                logger.error("[Finance MCP] Authentication failed")
                return "Finance API authentication failed."
            else:
                logger.warning(f"[Finance MCP] API returned {resp.status_code}")
                return f"Finance API error: HTTP {resp.status_code}"
        except Exception as e:
            logger.error(f"[Finance MCP] Error: {e}")
            return f"Finance API error: {str(e)}"


class HRMCPServer(MCPServer):
    """HR Advisor MCP Server - handles HR policies and employee matters"""
    
    def __init__(self, config: Dict[str, Any], api_spec: Dict[str, Any] = None):
        super().__init__(
            name="hr",
            description="HR policies, benefits, leave, employee matters, work policies, holidays",
            config=config
        )
        self.api_spec = api_spec
        self.use_mock = config.get('use_mock_responses', 'true').lower() == 'true'
        self.url = config.get('hr_agent_url')
        self.username = config.get('hr_agent_username')
        self.password = config.get('hr_agent_password')
        self.timeout = int(config.get('api_timeout', '30'))
    
    def handle_request(self, query: str) -> str:
        """Handle HR queries via ORDS GenAI Module"""
        logger.info(f"[HR MCP] Processing: {query}")
        
        if self.use_mock or not self.url:
            logger.info("[HR MCP] Using mock response")
            return "Our work-from-home policy allows 3 days remote work per week with core hours from 10 AM to 4 PM."
        
        try:
            params = {"prompt": query}
            headers = {"Accept": "application/json"}
            auth = HTTPBasicAuth(self.username, self.password) if self.username else None
            
            logger.info(f"[HR MCP] Calling ORDS API: {self.url}")
            resp = requests.get(self.url, params=params, headers=headers, auth=auth, timeout=self.timeout)
            
            if resp.status_code == 200:
                data = resp.json()
                # Handle list response
                if isinstance(data, list) and len(data) > 0:
                    top_items = data[:10]
                    formatted = []
                    for idx, item in enumerate(top_items, 1):
                        item_str = f"{idx}. " + ", ".join([f"{k}: {v}" for k, v in item.items()])
                        formatted.append(item_str)
                    result_text = "\n".join(formatted)
                    if len(data) > 10:
                        result_text += f"\n\n💡 Showing first 10 of {len(data)} records."
                    return result_text
                
                result = data.get('query_result', data.get('response', data.get('reply', data.get('answer'))))
                if result:
                    logger.info("[HR MCP] API call successful")
                    return result
            
            logger.warning(f"[HR MCP] API returned {resp.status_code}")
            return "HR agent API unavailable."
        except Exception as e:
            logger.error(f"[HR MCP] Error: {e}")
            return f"HR agent error: {str(e)}"


class OrdersMCPServer(MCPServer):
    """Orders Advisor MCP Server - handles sales orders via Fusion SCM REST"""
    
    def __init__(self, config: Dict[str, Any], api_spec: Dict[str, Any] = None):
        super().__init__(
            name="orders",
            description="Sales orders, inventory, delivery, returns, shipping, stock, products",
            config=config
        )
        self.api_spec = api_spec
        self.use_mock = config.get('use_mock_responses', 'true').lower() == 'true'
        self.url = config.get('orders_agent_url')
        self.username = config.get('orders_agent_username')
        self.password = config.get('orders_agent_password')
        self.timeout = int(config.get('api_timeout', '30'))
    
    def handle_request(self, query: str) -> str:
        """Handle orders queries via Fusion SCM REST API"""
        logger.info(f"[Orders MCP] Processing: {query}")
        
        if self.use_mock:
            logger.info("[Orders MCP] Using mock response")
            return "Current order fulfillment rate is at 95% with average delivery time of 2.3 days."
        
        if not self.url or not self.username or not self.password:
            logger.warning("[Orders MCP] API not configured")
            return "Orders API not configured."
        
        try:
            # Check for specific order key/ID
            order_key = None
            m = re.search(r"\b[A-Z]{2,10}:\d{9,}\b", query)
            if m:
                order_key = m.group(0)
            else:
                m2 = re.search(r"\b\d{9,15}\b", query)
                if m2:
                    order_key = m2.group(0)
            
            headers = {"Accept": "application/json"}
            auth = HTTPBasicAuth(self.username, self.password)
            
            if order_key:
                # Fetch specific order detail
                url = f"{self.url}/{order_key}"
                logger.info(f"[Orders MCP] Fetching detail: {url}")
                resp = requests.get(url, headers=headers, auth=auth, timeout=self.timeout, verify=True)
                
                if resp.status_code == 200:
                    data = resp.json()
                    ok = data.get('OrderKey', order_key)
                    status = data.get('StatusCode', 'N/A')
                    submitted_by = data.get('SubmittedBy', 'N/A')
                    submitted_date = data.get('SubmittedDate', 'N/A')
                    lines = data.get('lines') or []
                    line_summaries = []
                    for ln in lines[:5]:
                        ln_num = ln.get('LineNumber')
                        item = ln.get('ItemNumber')
                        qty = ln.get('OrderedQuantity')
                        line_summaries.append(f"Line {ln_num}: {item} x{qty}")
                    lines_text = "\n".join(line_summaries) if line_summaries else "(No line details)"
                    return (
                        f"Order {ok}\n"
                        f"Status: {status}\n"
                        f"Submitted By: {submitted_by} on {submitted_date}\n\n"
                        f"Top Lines:\n{lines_text}"
                    )
                elif resp.status_code == 404:
                    return f"No sales order found for '{order_key}'."
                elif resp.status_code == 401:
                    return "Orders API authentication failed."
                else:
                    return f"Orders API error: HTTP {resp.status_code}"
            else:
                # Fetch list of orders
                params = {"limit": 10}
                logger.info(f"[Orders MCP] Fetching list: {self.url}")
                resp = requests.get(self.url, params=params, headers=headers, auth=auth, timeout=self.timeout, verify=True)
                
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get('items') or []
                    if not items:
                        return "No recent sales orders found."
                    
                    # Sort by LastUpdateDate descending
                    def _parse_dt(s):
                        try:
                            return datetime.fromisoformat(s.replace('Z', '+00:00')) if isinstance(s, str) else datetime.min
                        except:
                            return datetime.min
                    items_sorted = sorted(items, key=lambda it: _parse_dt(it.get('LastUpdateDate')), reverse=True)
                    
                    display_items = items_sorted[:10]
                    lines = []
                    for it in display_items:
                        ok = it.get('OrderKey', 'N/A')
                        status = it.get('StatusCode', 'N/A')
                        created_by = it.get('CreatedBy', 'N/A')
                        last_upd = it.get('LastUpdateDate', 'N/A')
                        lines.append(f"• {ok} | Status: {status} | By: {created_by} | Updated: {last_upd}")
                    
                    result_text = f"Recent Sales Orders (showing 10 of {len(items_sorted)}):\n" + "\n".join(lines)
                    if len(items_sorted) > 10:
                        result_text += f"\n\n💡 Showing first 10 of {len(items_sorted)} orders."
                    return result_text
                elif resp.status_code == 401:
                    return "Orders API authentication failed."
                else:
                    return f"Orders API error: HTTP {resp.status_code}"
        except Exception as e:
            logger.error(f"[Orders MCP] Error: {e}")
            return f"Orders API error: {str(e)}"


class ReportsMCPServer(MCPServer):
    """Reports Advisor MCP Server - handles OAC workbook exports"""
    
    def __init__(self, config: Dict[str, Any], api_spec: Dict[str, Any] = None):
        super().__init__(
            name="reports",
            description="Analytics, workbooks, dashboards, OAC exports, visualizations",
            config=config
        )
        self.api_spec = api_spec
        self.use_mock = config.get('use_mock_responses', 'true').lower() == 'true'
        self.url = config.get('reports_agent_url')
        self.username = config.get('reports_agent_username')
        self.password = config.get('reports_agent_password')
        self.timeout = int(config.get('api_timeout', '30'))
    
    def handle_request(self, query: str) -> str:
        """Handle reports queries via OAC Workbook Export API"""
        logger.info(f"[Reports MCP] Processing: {query}")
        
        if self.use_mock:
            logger.info("[Reports MCP] Using mock response")
            return "Your OAC workbook export is being prepared. This typically takes a few moments."
        
        if not self.url or not self.username or not self.password:
            logger.warning("[Reports MCP] API not configured")
            return "Reports API not configured."
        
        try:
            api_version = "20210901"
            workbook_id = "L3NoYXJlZC9ST0lDL0Fic2VuY2UgV29ya2Jvb2s"
            export_format = "pdf"
            pages = ["canvas1"]
            
            # Step 1: Initiate export
            export_url = f"{self.url}/api/{api_version}/catalog/workbooks/{workbook_id}/exports"
            payload = {"format": export_format, "pages": pages}
            headers = {"Content-Type": "application/json", "Accept": "application/json"}
            auth = HTTPBasicAuth(self.username, self.password)
            
            logger.info(f"[Reports MCP] Initiating export: {export_url}")
            resp = requests.post(export_url, json=payload, headers=headers, auth=auth, timeout=self.timeout, verify=True)
            
            if resp.status_code != 202:
                logger.warning(f"[Reports MCP] Export returned {resp.status_code}")
                if resp.status_code == 401:
                    return "Reports API authentication failed."
                return f"Reports export error: HTTP {resp.status_code}"
            
            export_data = resp.json()
            export_id = export_data.get('exportId')
            if not export_id:
                return "Reports API did not return export ID."
            
            # Step 2: Poll status
            status_url = f"{self.url}/api/{api_version}/catalog/workbooks/{workbook_id}/exports/{export_id}/status"
            max_polls = 30
            poll_interval = 2
            
            for attempt in range(max_polls):
                logger.info(f"[Reports MCP] Polling status (attempt {attempt + 1}/{max_polls})")
                status_resp = requests.get(status_url, headers={"Accept": "application/json"}, auth=auth, timeout=self.timeout, verify=True)
                
                if status_resp.status_code != 200:
                    return f"Reports status check error: HTTP {status_resp.status_code}"
                
                status_data = status_resp.json()
                status = status_data.get('status')
                
                if status == "COMPLETED":
                    logger.info("[Reports MCP] Export completed")
                    break
                elif status == "FAILED":
                    error_msg = status_data.get('errorMessage', 'Unknown error')
                    return f"Reports export failed: {error_msg}"
                elif status == "IN_PROGRESS":
                    time.sleep(poll_interval)
                else:
                    time.sleep(poll_interval)
            else:
                return "Reports export timeout."
            
            # Step 3: Download
            download_url = f"{self.url}/api/{api_version}/catalog/workbooks/{workbook_id}/exports/{export_id}"
            logger.info(f"[Reports MCP] Downloading: {download_url}")
            download_resp = requests.get(download_url, auth=auth, timeout=self.timeout, verify=True)
            
            if download_resp.status_code != 200:
                return f"Reports download error: HTTP {download_resp.status_code}"
            
            report_b64 = base64.b64encode(download_resp.content).decode('utf-8')
            logger.info(f"[Reports MCP] Report downloaded ({len(report_b64)} chars)")
            return f"REPORT_DOWNLOAD:Reports:{export_format.upper()}:{report_b64}"
        except Exception as e:
            logger.error(f"[Reports MCP] Error: {e}")
            return f"Reports API error: {str(e)}"
