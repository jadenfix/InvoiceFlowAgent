#!/bin/bash

# Exception Service Test Runner
set -e

echo "🧪 Running Exception Service Tests"
echo "================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Check if we're in the right directory
if [ ! -f "app/main.py" ]; then
    print_error "Please run this script from the services/exception directory"
    exit 1
fi

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    print_warning "Virtual environment not detected. Consider activating one."
fi

# Install dependencies if needed
if [ ! -d "venv" ] && [ -z "$VIRTUAL_ENV" ]; then
    print_status "Creating virtual environment..."
    python -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
fi

# Check Docker availability for integration tests
if ! command -v docker &> /dev/null; then
    print_warning "Docker not found. Integration tests will be skipped."
    SKIP_INTEGRATION=true
else
    if ! docker info &> /dev/null; then
        print_warning "Docker daemon not running. Integration tests will be skipped."
        SKIP_INTEGRATION=true
    else
        print_status "Docker available for integration tests"
        SKIP_INTEGRATION=false
    fi
fi

# Parse command line arguments
RUN_UNIT=true
RUN_INTEGRATION=true
VERBOSE=false
COVERAGE=true

while [[ $# -gt 0 ]]; do
    case $1 in
        --unit-only)
            RUN_INTEGRATION=false
            shift
            ;;
        --integration-only)
            RUN_UNIT=false
            shift
            ;;
        --no-coverage)
            COVERAGE=false
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --unit-only        Run only unit tests"
            echo "  --integration-only Run only integration tests"
            echo "  --no-coverage      Skip coverage reporting"
            echo "  -v, --verbose      Verbose output"
            echo "  -h, --help         Show this help message"
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Skip integration tests if Docker is not available
if [ "$SKIP_INTEGRATION" = true ]; then
    RUN_INTEGRATION=false
fi

# Build pytest command
PYTEST_CMD="pytest"

if [ "$VERBOSE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD -v -s"
else
    PYTEST_CMD="$PYTEST_CMD -q"
fi

if [ "$COVERAGE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD --cov=app --cov-report=term-missing --cov-report=html --cov-fail-under=95"
fi

# Run linting first
print_status "Running code quality checks..."

# Check if flake8 is available
if command -v flake8 &> /dev/null; then
    echo "Running flake8..."
    flake8 app/ --max-line-length=100 --exclude=__pycache__,migrations
else
    print_warning "flake8 not found, skipping linting"
fi

# Check if black is available
if command -v black &> /dev/null; then
    echo "Checking code formatting with black..."
    black --check app/ --line-length=100
else
    print_warning "black not found, skipping format check"
fi

# Run unit tests
if [ "$RUN_UNIT" = true ]; then
    print_status "Running unit tests..."
    $PYTEST_CMD tests/unit/ -m "not slow"
    
    if [ $? -eq 0 ]; then
        print_status "Unit tests passed!"
    else
        print_error "Unit tests failed!"
        exit 1
    fi
fi

# Run integration tests
if [ "$RUN_INTEGRATION" = true ]; then
    print_status "Running integration tests..."
    echo "This may take a few minutes as Docker containers are started..."
    
    $PYTEST_CMD tests/integration/ --timeout=300
    
    if [ $? -eq 0 ]; then
        print_status "Integration tests passed!"
    else
        print_error "Integration tests failed!"
        exit 1
    fi
fi

# Generate coverage report
if [ "$COVERAGE" = true ]; then
    print_status "Coverage report generated in htmlcov/index.html"
fi

# Run type checking if mypy is available
if command -v mypy &> /dev/null; then
    print_status "Running type checking..."
    mypy app/ --ignore-missing-imports
else
    print_warning "mypy not found, skipping type checking"
fi

print_status "All tests completed successfully! 🎉"

# Performance tests (optional)
if [ -f "tests/performance/test_load.py" ]; then
    echo ""
    echo "To run performance tests:"
    echo "pytest tests/performance/ -v"
fi 