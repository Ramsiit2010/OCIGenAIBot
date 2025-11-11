"""
Base MCP Server class for RCOE Gen AI Agents
Each advisor (General, Finance, HR, Orders, Reports) registers as an MCP server
"""
import logging
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class MCPServer(ABC):
    """Base class for MCP servers representing advisors"""
    
    def __init__(self, name: str, description: str, config: Dict[str, Any]):
        """
        Initialize MCP server
        
        Args:
            name: Server name (e.g., "general", "finance")
            description: Server description for registration
            config: Configuration dict from config.properties
        """
        self.name = name
        self.description = description
        self.config = config
        self.is_registered = False
        logger.info(f"Initializing MCP Server: {name}")
    
    def register(self) -> bool:
        """
        Register this MCP server
        
        Returns:
            bool: True if registration successful
        """
        try:
            logger.info(f"Registering MCP server: {self.name}")
            self.is_registered = True
            logger.info(f"✓ MCP server registered: {self.name} - {self.description}")
            return True
        except Exception as e:
            logger.error(f"Failed to register MCP server {self.name}: {e}")
            return False
    
    def unregister(self):
        """Unregister this MCP server"""
        logger.info(f"Unregistering MCP server: {self.name}")
        self.is_registered = False
    
    @abstractmethod
    def handle_request(self, query: str) -> str:
        """
        Handle a query routed to this MCP server
        
        Args:
            query: User query string
            
        Returns:
            str: Response from this advisor
        """
        pass
    
    def get_server_info(self) -> Dict[str, Any]:
        """
        Get server metadata
        
        Returns:
            dict: Server information
        """
        return {
            "name": self.name,
            "description": self.description,
            "registered": self.is_registered
        }
