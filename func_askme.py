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
def get_finance_report(query: str) -> Dict[str, str]:
    """Get financial reports from BI Publisher"""
    return {"query": query, "status": "Report generation initiated", "advisor": "Finance"}

@tool
def get_hr_info(query: str) -> Dict[str, str]:
    """Get HR policies and employee information"""
    return {"query": query, "status": "HR query processed", "advisor": "HR"}

@tool
def get_order_status(query: str) -> Dict[str, str]:
    """Get sales order information from Fusion SCM"""
    return {"query": query, "status": "Order query processed", "advisor": "Orders"}

@tool
def get_analytics_report(query: str) -> Dict[str, str]:
    """Get analytics reports from Oracle Analytics Cloud"""
    return {"query": query, "status": "Analytics export initiated", "advisor": "Reports"}

@tool
def get_general_help(query: str) -> Dict[str, str]:
    """Get general help and route to appropriate advisor"""
    return {"query": query, "status": "General query processed", "advisor": "General"}

def handler(ctx, data: io.BytesIO = None):
    """
    OCI Functions handler for AskMeChatBot with Hybrid Intent Routing
    Supports keyword-based + Gen AI intent detection for multi-advisor system
    """
    agentEndpointId = None
    try:
        cfg = dict(ctx.Config())
        
        # Accessing custom variables
        agentEndpointId = cfg.get("agentEndpointId")
        genai_intent_mode = cfg.get("genaiIntentMode", "auto")

    except (Exception, ValueError) as ex:
        logging.getLogger().info('Issue getting function variables: ' + str(ex))
        return response.Response(
            ctx, response_data=json.dumps(
                {"message": "Exception occurred setting function variables"}),
            headers={"Content-Type": "application/json"}
        )

    try:
        print("Running AskMeChatBot handler")
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
            region="us-chicago-1"  # Gen AI region for AskMeChatBot
        )

        # Configure agent with all advisor tools
        agent = Agent(
            client=client,
            agent_endpoint_id=agentEndpointId,
            tools=[
                get_general_help,
                get_finance_report,
                get_hr_info,
                get_order_status,
                get_analytics_report
            ]
        )

        # Run the agent with user input
        result = agent.run(prompt, session_id=session_id)
        answer = result.output
        
    except (Exception, ValueError) as ex:
        logging.getLogger().info('error processing AskMeChatBot request: ' + str(ex))
        return response.Response(
            ctx, response_data=json.dumps(
                {"message": "Exception occurred processing user prompt"}),
            headers={"Content-Type": "application/json"}
        )

    return response.Response(
        ctx, response_data=json.dumps(
            {"message": "{0}".format(answer), "sessionId": session_id}),
        headers={"Content-Type": "application/json"}
    )
