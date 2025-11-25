import io
import json
import logging
from typing import Dict

from oci.addons.adk import Agent, AgentClient, tool
import oci

from fdk import response

signer = oci.auth.signers.get_resource_principals_signer()

agentClient = oci.generative_ai_agent.GenerativeAiAgentClient(
    config={},
    signer=signer
)

@tool
def general_mcp_server(query: str) -> Dict[str, str]:
    """MCP Server for general inquiries and ORDS GenAI Module queries"""
    return {"query": query, "status": "General MCP processed", "server": "GeneralMCPServer"}

@tool
def finance_mcp_server(query: str) -> Dict[str, str]:
    """MCP Server for financial reports via BI Publisher SOAP API"""
    return {"query": query, "status": "Finance MCP processed", "server": "FinanceMCPServer"}

@tool
def hr_mcp_server(query: str) -> Dict[str, str]:
    """MCP Server for HR policies and employee data via ORDS GenAI Module"""
    return {"query": query, "status": "HR MCP processed", "server": "HRMCPServer"}

@tool
def orders_mcp_server(query: str) -> Dict[str, str]:
    """MCP Server for sales orders via Fusion SCM REST API"""
    return {"query": query, "status": "Orders MCP processed", "server": "OrdersMCPServer"}

@tool
def reports_mcp_server(query: str) -> Dict[str, str]:
    """MCP Server for analytics reports via Oracle Analytics Cloud (30s wait + 3 retries)"""
    return {"query": query, "status": "Reports MCP processed", "server": "ReportsMCPServer"}

def handler(ctx, data: io.BytesIO = None):
    """
    OCI Functions handler for RCOEGenAIAgents with Pure Gen AI Intent Routing
    Uses MCP (Model Context Protocol) architecture with 5 specialized servers
    """
    agentEndpointId = None
    try:
        cfg = dict(ctx.Config())
        
        # Accessing custom variables
        agentEndpointId = cfg.get("agentEndpointId")
        genai_intent_mode = cfg.get("genaiIntentMode", "force")
        
    except (Exception, ValueError) as ex:
        logging.getLogger().info('Issue getting function variables: ' + str(ex))
        return response.Response(
            ctx, response_data=json.dumps(
                {"message": "Exception occurred setting function variables"}),
            headers={"Content-Type": "application/json"}
        )

    try:
        print("Running RCOEGenAIAgents MCP handler")
        body = json.loads(data.getvalue())
        try:
            session_id = body.get("sessionId")
            print("sessionId:", session_id)
            prompt = body.get("prompt")
            print("prompt:", prompt)
        except Exception as e:
            logging.getLogger().info('Issue parsing prompt or session id: ' + str(e))

        client = AgentClient(
            auth_type="resource_principal",
            region="us-chicago-1"  # Gen AI region for RCOEGenAIAgents
        )

        # Configure agent with all MCP server tools
        agent = Agent(
            client=client,
            agent_endpoint_id=agentEndpointId,
            tools=[
                general_mcp_server,
                finance_mcp_server,
                hr_mcp_server,
                orders_mcp_server,
                reports_mcp_server
            ]
        )

        # Run the agent with pure Gen AI intent detection
        result = agent.run(prompt, session_id=session_id)
        answer = result.output
        
        # Log MCP server routing
        print(f"[MCP Routing] Intent detected and routed to appropriate MCP server")
        
    except (Exception, ValueError) as ex:
        logging.getLogger().info('error processing RCOEGenAIAgents MCP request: ' + str(ex))
        return response.Response(
            ctx, response_data=json.dumps(
                {"message": "Exception occurred processing user prompt"}),
            headers={"Content-Type": "application/json"}
        )

    return response.Response(
        ctx, response_data=json.dumps(
            {
                "message": "{0}".format(answer),
                "sessionId": session_id,
                "architecture": "MCP"
            }),
        headers={"Content-Type": "application/json"}
    )
