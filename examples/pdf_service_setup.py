#!/usr/bin/env python3
"""
Complete setup example for a secure PDF processing service
This shows how to deploy Berry MCP with OAuth2 authentication for PDF tools
"""

import asyncio
import logging
import os
from pathlib import Path

from berry_mcp import MCPServer
from berry_mcp.auth import FileTokenStorage, OAuth2Config, OAuth2Manager
from berry_mcp.core import EnhancedSSETransport
from berry_mcp.elicitation import ElicitationManager, SSEElicitationHandler


class SecurePDFService:
    """Secure PDF processing service with OAuth2 authentication"""

    def __init__(self):
        self.server = MCPServer(name="secure-pdf-service")
        self.oauth_manager = None
        self.elicitation_manager = None
        self.setup_logging()

    def setup_logging(self):
        """Configure logging for the service"""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

    def setup_oauth2(self, provider: str = "google"):
        """Setup OAuth2 authentication for different providers"""

        if provider == "google":
            oauth_config = OAuth2Config(
                client_id=os.getenv("GOOGLE_CLIENT_ID", "your_google_client_id"),
                client_secret=os.getenv(
                    "GOOGLE_CLIENT_SECRET", "your_google_client_secret"
                ),
                authorization_url="https://accounts.google.com/o/oauth2/auth",
                token_url="https://oauth2.googleapis.com/token",
                redirect_uri="http://localhost:8080/oauth/callback",
                scope="openid profile email",
                use_pkce=True,
            )
        elif provider == "github":
            oauth_config = OAuth2Config(
                client_id=os.getenv("GITHUB_CLIENT_ID", "your_github_client_id"),
                client_secret=os.getenv(
                    "GITHUB_CLIENT_SECRET", "your_github_client_secret"
                ),
                authorization_url="https://github.com/login/oauth/authorize",
                token_url="https://github.com/login/oauth/access_token",
                redirect_uri="http://localhost:8080/oauth/callback",
                scope="user:email",
                use_pkce=False,  # GitHub doesn't require PKCE
            )
        else:
            raise ValueError(f"Unsupported OAuth provider: {provider}")

        # Create OAuth manager with persistent token storage
        self.oauth_manager = OAuth2Manager(oauth_config)

        # Setup file-based token storage for persistence
        _token_storage = FileTokenStorage(
            storage_path=Path.home() / ".berry_mcp" / "tokens.json"
        )

        return oauth_config

    def setup_transport_and_elicitation(
        self, host: str = "localhost", port: int = 8080
    ):
        """Setup enhanced transport with OAuth2 and elicitation"""

        # Create enhanced transport
        transport = EnhancedSSETransport(
            host=host,
            port=port,
            oauth_manager=self.oauth_manager,
            require_auth=True,  # Require authentication for all requests
        )

        # Setup elicitation manager for user interactions
        self.elicitation_manager = ElicitationManager(
            handler=SSEElicitationHandler(transport),
            default_timeout=300,  # 5 minutes default timeout
        )

        return transport

    def register_pdf_tools(self):
        """Register secure PDF processing tools"""

        @self.server.tool
        async def secure_pdf_extract(
            file_path: str, page_limit: int = 20, require_confirmation: bool = True
        ) -> dict:
            """
            Securely extract text from PDF with user confirmation

            Args:
                file_path: Path to the PDF file
                page_limit: Maximum pages to process
                require_confirmation: Whether to ask user for confirmation
            """

            # Validate file path and existence
            if not os.path.exists(file_path):
                return {"error": "File not found", "file_path": file_path}

            if not file_path.lower().endswith(".pdf"):
                return {"error": "File must be a PDF", "file_path": file_path}

            file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB

            # Ask user for permission if file is large or confirmation required
            if require_confirmation or file_size > 10:  # 10MB threshold
                if self.elicitation_manager:
                    confirmed = await self.elicitation_manager.prompt_confirmation(
                        title="PDF Processing Authorization",
                        message=f"Process PDF file: {file_path}?\nFile size: {file_size:.1f}MB\nPage limit: {page_limit}",
                        default=False,
                        timeout=120,
                    )

                    if not confirmed:
                        return {
                            "status": "cancelled",
                            "message": "PDF processing cancelled by user",
                            "file_path": file_path,
                        }

            try:
                # Import PDF tools dynamically
                from berry_mcp.tools.pdf_tools import read_pdf_text

                # Process the PDF
                result = await read_pdf_text(file_path, page_limit)

                return {
                    "status": "success",
                    "file_path": file_path,
                    "content": result,
                    "file_size_mb": file_size,
                    "processed_pages": min(
                        page_limit, self._get_pdf_page_count(file_path)
                    ),
                }

            except Exception as e:
                logging.error(f"PDF processing error: {e}")
                return {"status": "error", "message": str(e), "file_path": file_path}

        @self.server.tool
        async def list_user_pdfs(directory: str = None) -> dict:  # noqa: F841
            """
            List PDF files available to the authenticated user

            Args:
                directory: Directory to search (defaults to user's home/Documents)
            """

            if not directory:
                directory = str(Path.home() / "Documents")

            # Ask user for permission to scan directory
            if self.elicitation_manager:
                confirmed = await self.elicitation_manager.prompt_confirmation(
                    title="Directory Access",
                    message=f"Scan directory for PDF files: {directory}?",
                    default=False,
                    timeout=60,
                )

                if not confirmed:
                    return {
                        "status": "cancelled",
                        "message": "Directory scan cancelled",
                    }

            try:
                pdf_files = []
                directory_path = Path(directory)

                if directory_path.exists() and directory_path.is_dir():
                    for pdf_file in directory_path.rglob("*.pdf"):
                        if pdf_file.is_file():
                            stat = pdf_file.stat()
                            pdf_files.append(
                                {
                                    "path": str(pdf_file),
                                    "name": pdf_file.name,
                                    "size_mb": stat.st_size / (1024 * 1024),
                                    "modified": stat.st_mtime,
                                }
                            )

                return {
                    "status": "success",
                    "directory": directory,
                    "pdf_count": len(pdf_files),
                    "files": sorted(
                        pdf_files, key=lambda x: x["modified"], reverse=True
                    ),
                }

            except Exception as e:
                return {"status": "error", "message": str(e)}

        @self.server.tool
        async def pdf_batch_process(  # noqa: F841
            file_patterns: list[str], max_files: int = 5
        ) -> dict:
            """
            Batch process multiple PDF files with user approval

            Args:
                file_patterns: List of file paths or glob patterns
                max_files: Maximum number of files to process
            """

            # Get list of files to process
            files_to_process = []
            for pattern in file_patterns:
                if os.path.exists(pattern) and pattern.endswith(".pdf"):
                    files_to_process.append(pattern)
                else:
                    # Handle glob patterns
                    from glob import glob

                    matches = glob(pattern)
                    pdf_matches = [f for f in matches if f.lower().endswith(".pdf")]
                    files_to_process.extend(pdf_matches)

            # Limit files
            files_to_process = files_to_process[:max_files]

            if not files_to_process:
                return {"status": "error", "message": "No PDF files found"}

            # Ask user for batch processing confirmation
            if self.elicitation_manager:
                file_list = "\n".join(
                    [f"• {os.path.basename(f)}" for f in files_to_process]
                )
                confirmed = await self.elicitation_manager.prompt_confirmation(
                    title="Batch PDF Processing",
                    message=f"Process {len(files_to_process)} PDF files?\n\nFiles:\n{file_list}",
                    default=False,
                    timeout=180,
                )

                if not confirmed:
                    return {
                        "status": "cancelled",
                        "message": "Batch processing cancelled",
                    }

            # Process files
            results = []
            for file_path in files_to_process:
                try:
                    result = await secure_pdf_extract(
                        file_path, require_confirmation=False
                    )
                    results.append(result)
                except Exception as e:
                    results.append(
                        {"status": "error", "file_path": file_path, "message": str(e)}
                    )

            successful = len([r for r in results if r.get("status") == "success"])

            return {
                "status": "completed",
                "total_files": len(files_to_process),
                "successful": successful,
                "failed": len(results) - successful,
                "results": results,
            }

    def _get_pdf_page_count(self, file_path: str) -> int:
        """Get PDF page count"""
        try:
            import PyPDF2

            with open(file_path, "rb") as file:
                reader = PyPDF2.PdfReader(file)
                return len(reader.pages)
        except Exception:
            return 1  # Fallback

    async def run_service(
        self, provider: str = "google", host: str = "localhost", port: int = 8080
    ):
        """Run the secure PDF service"""

        print("🚀 Starting Secure PDF Service...")
        print(f"📡 Host: {host}:{port}")
        print(f"🔐 OAuth Provider: {provider}")

        # Setup OAuth2
        _oauth_config = self.setup_oauth2(provider)
        print(f"✅ OAuth2 configured for {provider}")

        # Setup transport and elicitation
        transport = self.setup_transport_and_elicitation(host, port)
        print("✅ Enhanced transport configured")

        # Register PDF tools
        self.register_pdf_tools()
        print("✅ PDF tools registered")

        # Connect and run server
        self.server.connect_transport(transport)
        print(f"🌐 Server starting at http://{host}:{port}")
        print(f"🔗 OAuth callback: http://{host}:{port}/oauth/callback")
        print("\n📋 Setup Instructions:")
        print(f"1. Create OAuth2 app with your {provider} provider")
        print(f"2. Set redirect URI to: http://{host}:{port}/oauth/callback")
        print("3. Set environment variables:")
        print(f"   - {provider.upper()}_CLIENT_ID=your_client_id")
        print(f"   - {provider.upper()}_CLIENT_SECRET=your_client_secret")
        print(f"4. Visit http://{host}:{port}/auth to authenticate")
        print(f"5. Configure VS Code MCP with: http://{host}:{port}")

        await self.server.run()


# Example usage and deployment configurations
async def main():
    """Main entry point for the PDF service"""

    # Create service instance
    service = SecurePDFService()

    # Get configuration from environment or defaults
    provider = os.getenv("OAUTH_PROVIDER", "google")  # google, github
    host = os.getenv("SERVICE_HOST", "localhost")
    port = int(os.getenv("SERVICE_PORT", "8080"))

    # Run the service
    await service.run_service(provider=provider, host=host, port=port)


if __name__ == "__main__":
    # Check for required dependencies
    try:
        import pymupdf  # noqa: F401
        import PyPDF2  # noqa: F401

        print("✅ PDF libraries available")
    except ImportError as e:
        print(f"❌ Missing PDF dependencies: {e}")
        print("Run: uv pip install pymupdf4llm PyPDF2")
        exit(1)

    # Run the service
    asyncio.run(main())
