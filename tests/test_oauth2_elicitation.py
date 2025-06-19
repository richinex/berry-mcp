"""
Tests for OAuth2 authentication and elicitation features
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from berry_mcp.auth import OAuth2Manager, OAuth2Config, TokenInfo
from berry_mcp.auth.exceptions import OAuth2FlowError, TokenExpiredError
from berry_mcp.elicitation import (
    ElicitationManager,
    PromptBuilder,
    ConsoleElicitationHandler,
    CapabilityBuilder
)
from berry_mcp.elicitation.prompts import PromptType


@pytest.fixture
def oauth_config():
    """Create OAuth2 configuration for testing"""
    return OAuth2Config(
        client_id="test_client",
        client_secret="test_secret",
        authorization_url="https://example.com/oauth/authorize",
        token_url="https://example.com/oauth/token",
        redirect_uri="http://localhost:8080/callback"
    )


@pytest.fixture
def oauth_manager(oauth_config):
    """Create OAuth2 manager for testing"""
    return OAuth2Manager(oauth_config)


@pytest.fixture
def token_info():
    """Create token info for testing"""
    return TokenInfo(
        access_token="test_access_token",
        token_type="Bearer",
        expires_in=3600,
        refresh_token="test_refresh_token",
        scope="read write"
    )


@pytest.fixture
def elicitation_manager():
    """Create elicitation manager for testing"""
    handler = ConsoleElicitationHandler(use_input=False)  # Disable input for testing
    return ElicitationManager(handler=handler)


class TestOAuth2Manager:
    """Test OAuth2 manager functionality"""
    
    def test_oauth2_config_creation(self, oauth_config):
        """Test OAuth2 config creation"""
        assert oauth_config.client_id == "test_client"
        assert oauth_config.client_secret == "test_secret"
        assert oauth_config.use_pkce is True
    
    def test_oauth2_manager_initialization(self, oauth_manager):
        """Test OAuth2 manager initialization"""
        assert oauth_manager.config.client_id == "test_client"
        assert oauth_manager._token_info is None
    
    def test_pkce_generation(self, oauth_manager):
        """Test PKCE code generation"""
        code_verifier, code_challenge = oauth_manager.generate_pkce_pair()
        
        assert len(code_verifier) >= 43
        assert len(code_challenge) >= 43
        assert code_verifier != code_challenge
    
    def test_authorization_url_building(self, oauth_manager):
        """Test authorization URL building"""
        auth_url, code_verifier = oauth_manager.build_authorization_url("test_state")
        
        assert "client_id=test_client" in auth_url
        assert "response_type=code" in auth_url
        assert "state=test_state" in auth_url
        assert "code_challenge=" in auth_url
        assert code_verifier is not None
    
    def test_token_info_creation(self, token_info):
        """Test token info creation"""
        assert token_info.access_token == "test_access_token"
        assert token_info.token_type == "Bearer"
        assert token_info.expires_in == 3600
        assert token_info.expires_at is not None
    
    def test_token_info_expiration(self, token_info):
        """Test token expiration checking"""
        # Fresh token should not be expired
        assert not token_info.is_expired()
        
        # Token with past expiration should be expired
        import time
        token_info.expires_at = time.time() - 100
        assert token_info.is_expired()
    
    def test_token_info_serialization(self, token_info):
        """Test token info serialization"""
        token_dict = token_info.to_dict()
        
        assert token_dict["access_token"] == "test_access_token"
        assert token_dict["token_type"] == "Bearer"
        
        # Test deserialization
        restored_token = TokenInfo.from_dict(token_dict)
        assert restored_token.access_token == token_info.access_token
        assert restored_token.expires_in == token_info.expires_in
    
    @pytest.mark.asyncio
    async def test_token_validation(self, oauth_manager):
        """Test token validation"""
        # Valid token
        assert await oauth_manager.validate_token("valid_token_string")
        
        # Invalid token
        assert not await oauth_manager.validate_token("")
        assert not await oauth_manager.validate_token("short")
    
    def test_token_management(self, oauth_manager, token_info):
        """Test token management operations"""
        # Set token
        oauth_manager.set_token_info(token_info)
        assert oauth_manager.get_token_info() == token_info
        
        # Clear token
        oauth_manager.clear_token_info()
        assert oauth_manager.get_token_info() is None
    
    @pytest.mark.asyncio
    async def test_get_valid_token_no_token(self, oauth_manager):
        """Test getting valid token when no token is available"""
        with pytest.raises(TokenExpiredError):
            await oauth_manager.get_valid_token()
    
    @pytest.mark.asyncio
    async def test_get_valid_token_expired_no_refresh(self, oauth_manager, token_info):
        """Test getting valid token when expired and no refresh token"""
        import time
        token_info.expires_at = time.time() - 100
        token_info.refresh_token = None
        
        oauth_manager.set_token_info(token_info)
        
        with pytest.raises(TokenExpiredError):
            await oauth_manager.get_valid_token()


class TestElicitationPrompts:
    """Test elicitation prompt functionality"""
    
    def test_confirmation_prompt_creation(self):
        """Test confirmation prompt creation"""
        prompt = PromptBuilder.confirmation(
            title="Test Confirmation",
            message="Do you want to proceed?",
            default=True,
            timeout=60
        )
        
        assert prompt.prompt_type == PromptType.CONFIRMATION
        assert prompt.title == "Test Confirmation"
        assert prompt.default_response is True
        assert prompt.timeout_seconds == 60
    
    def test_confirmation_prompt_validation(self):
        """Test confirmation prompt response validation"""
        prompt = PromptBuilder.confirmation("Test", "Message")
        
        assert prompt.validate_response(True)
        assert prompt.validate_response(False)
        assert not prompt.validate_response("yes")
        assert not prompt.validate_response(1)
    
    def test_input_prompt_creation(self):
        """Test input prompt creation"""
        prompt = PromptBuilder.text_input(
            title="Test Input",
            message="Enter text:",
            placeholder="Type here...",
            default="default_value",
            max_length=100,
            pattern=r"^\w+$"
        )
        
        assert prompt.prompt_type == PromptType.INPUT
        assert prompt.placeholder == "Type here..."
        assert prompt.default_value == "default_value"
        assert prompt.max_length == 100
        assert prompt.pattern == r"^\w+$"
    
    def test_input_prompt_validation(self):
        """Test input prompt response validation"""
        prompt = PromptBuilder.text_input(
            "Test", "Message", max_length=10, pattern=r"^\w+$"
        )
        
        assert prompt.validate_response("valid")
        assert prompt.validate_response("test123")
        assert not prompt.validate_response("toolongtext")  # Exceeds max_length
        assert not prompt.validate_response("invalid-text")  # Doesn't match pattern
        assert not prompt.validate_response(123)  # Not a string
    
    def test_choice_prompt_creation(self):
        """Test choice prompt creation"""
        choices = [("opt1", "Option 1"), ("opt2", "Option 2")]
        prompt = PromptBuilder.single_choice(
            title="Test Choice",
            message="Select an option:",
            choices=choices
        )
        
        assert prompt.prompt_type == PromptType.CHOICE
        assert len(prompt.choices) == 2
        assert prompt.allow_multiple is False
        assert prompt.choices[0]["value"] == "opt1"
        assert prompt.choices[0]["label"] == "Option 1"
    
    def test_choice_prompt_validation(self):
        """Test choice prompt response validation"""
        choices = [("opt1", "Option 1"), ("opt2", "Option 2")]
        
        # Single choice prompt
        single_prompt = PromptBuilder.single_choice("Test", "Message", choices)
        assert single_prompt.validate_response("opt1")
        assert single_prompt.validate_response("opt2")
        assert not single_prompt.validate_response("opt3")  # Invalid choice
        assert not single_prompt.validate_response(["opt1"])  # Should be string
        
        # Multiple choice prompt
        multi_prompt = PromptBuilder.multiple_choice(
            "Test", "Message", choices, min_selections=1, max_selections=2
        )
        assert multi_prompt.validate_response(["opt1"])
        assert multi_prompt.validate_response(["opt1", "opt2"])
        assert not multi_prompt.validate_response([])  # Below min_selections
        assert not multi_prompt.validate_response(["opt1", "opt2", "opt3"])  # Invalid choice
        assert not multi_prompt.validate_response("opt1")  # Should be list
    
    def test_file_selection_prompt_creation(self):
        """Test file selection prompt creation"""
        prompt = PromptBuilder.file_selection(
            title="Select File",
            message="Choose a file:",
            file_types=[".txt", ".json"],
            allow_multiple=True,
            start_directory="/home/user"
        )
        
        assert prompt.prompt_type == PromptType.FILE_SELECTION
        assert prompt.file_types == [".txt", ".json"]
        assert prompt.allow_multiple is True
        assert prompt.start_directory == "/home/user"
    
    def test_prompt_to_mcp_message(self):
        """Test prompt conversion to MCP message"""
        prompt = PromptBuilder.confirmation("Test", "Message", default=True)
        message = prompt.to_mcp_message()
        
        assert message["jsonrpc"] == "2.0"
        assert message["method"] == "notifications/elicitation"
        assert message["params"]["type"] == "confirmation"
        assert message["params"]["title"] == "Test"
        assert message["params"]["default"] is True


class TestElicitationManager:
    """Test elicitation manager functionality"""
    
    @pytest.mark.asyncio
    async def test_elicitation_manager_initialization(self, elicitation_manager):
        """Test elicitation manager initialization"""
        assert elicitation_manager.handler is not None
        assert elicitation_manager.default_timeout == 300
        assert len(elicitation_manager._active_prompts) == 0
    
    @pytest.mark.asyncio
    async def test_prompt_confirmation(self, elicitation_manager):
        """Test confirmation prompt"""
        # Mock handler to return True
        elicitation_manager.handler = AsyncMock()
        elicitation_manager.handler.handle_prompt = AsyncMock(return_value=True)
        
        result = await elicitation_manager.prompt_confirmation(
            "Test", "Proceed?", default=False
        )
        
        assert result is True
        elicitation_manager.handler.handle_prompt.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_prompt_input(self, elicitation_manager):
        """Test input prompt"""
        # Mock handler to return test string
        elicitation_manager.handler = AsyncMock()
        elicitation_manager.handler.handle_prompt = AsyncMock(return_value="test input")
        
        result = await elicitation_manager.prompt_input(
            "Test", "Enter text:", default="default"
        )
        
        assert result == "test input"
        elicitation_manager.handler.handle_prompt.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_prompt_choice(self, elicitation_manager):
        """Test choice prompt"""
        # Mock handler to return choice
        elicitation_manager.handler = AsyncMock()
        elicitation_manager.handler.handle_prompt = AsyncMock(return_value="option1")
        
        choices = [("option1", "Option 1"), ("option2", "Option 2")]
        result = await elicitation_manager.prompt_choice(
            "Test", "Choose:", choices
        )
        
        assert result == "option1"
        elicitation_manager.handler.handle_prompt.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_prompt_file_selection(self, elicitation_manager):
        """Test file selection prompt"""
        # Mock handler to return file path
        elicitation_manager.handler = AsyncMock()
        elicitation_manager.handler.handle_prompt = AsyncMock(return_value="/path/to/file.txt")
        
        result = await elicitation_manager.prompt_file_selection(
            "Test", "Select file:", file_types=[".txt"]
        )
        
        assert result == "/path/to/file.txt"
        elicitation_manager.handler.handle_prompt.assert_called_once()
    
    def test_capability_registration(self, elicitation_manager):
        """Test capability registration"""
        capability = CapabilityBuilder.create_file_tool_capability(
            "test_tool", "Test tool description"
        )
        
        elicitation_manager.register_capability(capability)
        
        assert len(elicitation_manager._capabilities) == 1
        assert elicitation_manager.get_capability("test_tool") == capability
    
    def test_capability_queries(self, elicitation_manager):
        """Test capability query methods"""
        file_cap = CapabilityBuilder.create_file_tool_capability(
            "file_tool", "File tool"
        )
        search_cap = CapabilityBuilder.create_search_tool_capability(
            "search_tool", "Search tool"
        )
        
        elicitation_manager.register_capability(file_cap)
        elicitation_manager.register_capability(search_cap)
        
        # Test list all
        all_caps = elicitation_manager.list_capabilities()
        assert len(all_caps) == 2
        
        # Test by category
        file_caps = elicitation_manager.get_capabilities_by_category("file_operations")
        assert len(file_caps) == 1
        assert file_caps[0].name == "file_tool"
        
        search_caps = elicitation_manager.get_capabilities_by_category("search")
        assert len(search_caps) == 1
        assert search_caps[0].name == "search_tool"
        
        # Test by tag
        file_tagged = elicitation_manager.get_capabilities_by_tag("files")
        assert len(file_tagged) == 1
        
        search_tagged = elicitation_manager.get_capabilities_by_tag("search")
        assert len(search_tagged) == 1


class TestConsoleElicitationHandler:
    """Test console elicitation handler"""
    
    @pytest.mark.asyncio
    async def test_console_handler_confirmation(self):
        """Test console handler confirmation prompt"""
        handler = ConsoleElicitationHandler(use_input=False)
        prompt = PromptBuilder.confirmation("Test", "Proceed?", default=True)
        
        result = await handler.handle_prompt(prompt)
        assert result is True  # Should return default
    
    @pytest.mark.asyncio
    async def test_console_handler_input(self):
        """Test console handler input prompt"""
        handler = ConsoleElicitationHandler(use_input=False)
        prompt = PromptBuilder.text_input("Test", "Enter:", default="default_value")
        
        result = await handler.handle_prompt(prompt)
        assert result == "default_value"  # Should return default
    
    @pytest.mark.asyncio
    async def test_console_handler_choice(self):
        """Test console handler choice prompt"""
        handler = ConsoleElicitationHandler(use_input=False)
        choices = [("opt1", "Option 1"), ("opt2", "Option 2")]
        prompt = PromptBuilder.single_choice("Test", "Choose:", choices)
        
        result = await handler.handle_prompt(prompt)
        assert result == "opt1"  # Should return first choice
    
    @pytest.mark.asyncio
    async def test_console_handler_timeout(self):
        """Test console handler timeout handling"""
        handler = ConsoleElicitationHandler(use_input=False)
        prompt = PromptBuilder.confirmation("Test", "Proceed?", default=False)
        
        result = await handler.handle_timeout(prompt)
        assert result is False  # Should return default
    
    @pytest.mark.asyncio
    async def test_console_handler_error(self):
        """Test console handler error handling"""
        handler = ConsoleElicitationHandler(use_input=False)
        prompt = PromptBuilder.input("Test", "Enter:")
        error = Exception("Test error")
        
        result = await handler.handle_error(prompt, error)
        assert result == ""  # Should return safe default


class TestCapabilityBuilder:
    """Test capability builder functionality"""
    
    def test_file_tool_capability(self):
        """Test file tool capability creation"""
        capability = CapabilityBuilder.create_file_tool_capability(
            "file_processor", "Process files", supports_streaming=True
        )
        
        assert capability.name == "file_processor"
        assert capability.category == "file_operations"
        assert "files" in capability.tags
        assert capability.supports_streaming is True
        assert capability.estimated_duration == "fast"
        assert capability.output_schema is not None
    
    def test_search_tool_capability(self):
        """Test search tool capability creation"""
        capability = CapabilityBuilder.create_search_tool_capability(
            "web_search", "Search the web", requires_auth=True
        )
        
        assert capability.name == "web_search"
        assert capability.category == "search"
        assert "search" in capability.tags
        assert capability.requires_authentication is True
        assert capability.estimated_duration == "medium"
    
    def test_api_tool_capability(self):
        """Test API tool capability creation"""
        capability = CapabilityBuilder.create_api_tool_capability(
            "api_client", "API client", dependencies=["requests"]
        )
        
        assert capability.name == "api_client"
        assert capability.category == "api"
        assert "api" in capability.tags
        assert "requests" in capability.dependencies
        assert capability.requires_authentication is True
        assert "network" in capability.resource_requirements
    
    def test_capability_to_dict(self):
        """Test capability serialization"""
        capability = CapabilityBuilder.create_file_tool_capability(
            "test_tool", "Test tool"
        )
        
        cap_dict = capability.to_dict()
        
        assert cap_dict["name"] == "test_tool"
        assert cap_dict["category"] == "file_operations"
        assert "output_schema" in cap_dict
        assert cap_dict["supports_streaming"] is False