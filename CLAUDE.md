always follow these principles: KISS, DRY, YAGNI, and SOLID

THE PATH TO WELL-DESIGNED SOFTWARE
ITERATE TO ACHIEVE GOOD DESIGN

PART 2: DESIGN THE RIGHT APPLICATION

GET REQUIREMENTS TO BUILD THE RIGHT APPLICATION
GOOD CLASS DESIGN TO BUILD THE APPLICATION RIGHT

PART 3: DESIGN THE APPLICATION RIGHT

HIDE CLASS IMPLEMENTATIONS
DON'T SURPRISE YOUR USERS
DESIGN SUBCLASSES RIGHT

PART 4: DESIGN PATTERNS SOLVE APPLICATION ARCHITECTURE PROBLEMS

THE TEMPLATE METHOD AND STRATEGY DESIGN PATTERNS
THE FACTORY METHOD AND ABSTRACT FACTORY DESIGN PATTERNS
THE ADAPTER AND FAÇADE DESIGN PATTERNS
THE ITERATOR AND VISITOR DESIGN PATTERNS
THE OBSERVER DESIGN PATTERN
THE STATE DESIGN PATTERN
THE SINGLETON, COMPOSITE, AND DECORATOR DESIGN PATTERNS

PART 5: ADDITIONAL DESIGN TECHNIQUES

DESIGNING SOLUTIONS WITH RECURSION AND BACKTRACKING
DESIGNING MULTITHREADED PROGRAMS

# Development Commands

## Setup and Installation
```bash
# Install dependencies
uv pip install -e ".[dev]"

# Install specific PDF dependencies
uv pip install pymupdf4llm PyPDF2
```

## Testing
```bash
# Run all tests
pytest tests/

# Run tests with coverage
pytest --cov=berry_pdf_mcp tests/

# Run specific test file
pytest tests/test_decorators.py -v

# Run tests in watch mode (if pytest-watch is installed)
ptw tests/
```

## Code Quality
```bash
# Format code
black src/ tests/ examples/

# Check formatting
black --check src/ tests/ examples/

# Lint code
ruff check src/ tests/ examples/

# Fix linting issues
ruff check --fix src/ tests/ examples/

# Type checking
mypy src/berry_pdf_mcp/

# Type checking with verbose output
mypy --verbose src/berry_pdf_mcp/
```

## Running the Server
```bash
# Run MCP server
python -m berry_pdf_mcp.server

# Run server with debug logging
BERRY_PDF_LOG_LEVEL=DEBUG python -m berry_pdf_mcp.server

# Run example usage
python examples/server_usage.py
```

## Development Workflow
```bash
# Full quality check before commit
black src/ tests/ examples/ && ruff check src/ tests/ examples/ && mypy src/ && pytest tests/

# Quick test run
pytest tests/ -x --tb=short

# Run examples to test functionality
python examples/server_usage.py
```

## Build and Distribution
```bash
# Build package
python -m build

# Check package
twine check dist/*

# Install locally for testing
uv pip install -e .
```