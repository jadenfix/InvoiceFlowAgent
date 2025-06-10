#!/bin/bash

# InvoiceFlow Pipeline Demo Script
# This script demonstrates the complete end-to-end pipeline from PDF upload to matching

set -e  # Exit on any error

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SAMPLE_PDF="$SCRIPT_DIR/sample_invoice.pdf"
DEMO_TIMEOUT=120  # 2 minutes timeout for the demo

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    if ! command -v curl &> /dev/null; then
        log_error "curl is not installed. Please install curl first."
        exit 1
    fi
    
    if ! command -v jq &> /dev/null; then
        log_warning "jq is not installed. JSON output will not be formatted."
    fi
    
    log_success "All prerequisites are available"
}

# Create sample PDF if it doesn't exist
create_sample_pdf() {
    if [[ ! -f "$SAMPLE_PDF" ]]; then
        log_info "Creating sample PDF for testing..."
        
        # Create a simple PDF with invoice-like content
        cat > "$SAMPLE_PDF" << 'EOF'
%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj

2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj

3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Contents 4 0 R
>>
endobj

4 0 obj
<<
/Length 200
>>
stream
BT
/F1 12 Tf
50 700 Td
(INVOICE) Tj
0 -30 Td
(Vendor: Test Vendor Corp) Tj
0 -20 Td
(Invoice #: INV-2024-001) Tj
0 -20 Td
(PO Number: PO-TEST-001) Tj
0 -20 Td
(Total Amount: $995.00) Tj
0 -20 Td
(Date: 2024-01-20) Tj
ET
endstream
endobj

xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000204 00000 n 
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
449
%%EOF
EOF
        
        log_success "Sample PDF created at $SAMPLE_PDF"
    else
        log_info "Using existing sample PDF at $SAMPLE_PDF"
    fi
}

# Build Docker images
build_images() {
    log_info "Building Docker images for all services..."
    
    cd "$PROJECT_ROOT"
    
    # Build each service
    services=("ingest" "extract" "match")
    
    for service in "${services[@]}"; do
        if [[ -d "services/$service" ]]; then
            log_info "Building $service service..."
            docker build -t "invoiceflow/$service:e2e" "services/$service/"
        else
            log_warning "Service directory services/$service not found, skipping..."
        fi
    done
    
    log_success "All Docker images built successfully"
}

# Start services using docker-compose
start_services() {
    log_info "Starting all services using docker-compose..."
    
    cd "$PROJECT_ROOT"
    
    # Stop any existing containers
    docker-compose -f docker-compose.e2e.yml down --remove-orphans || true
    
    # Start services
    docker-compose -f docker-compose.e2e.yml up -d
    
    log_info "Waiting for services to become healthy..."
    
    # Wait for health checks to pass
    timeout=60
    elapsed=0
    
    while [[ $elapsed -lt $timeout ]]; do
        if docker-compose -f docker-compose.e2e.yml ps | grep -q "healthy"; then
            # Check if all required services are healthy
            ingest_health=$(docker inspect invoiceflow-ingest-e2e --format='{{.State.Health.Status}}' 2>/dev/null || echo "unknown")
            extract_health=$(docker inspect invoiceflow-extract-e2e --format='{{.State.Health.Status}}' 2>/dev/null || echo "unknown")
            match_health=$(docker inspect invoiceflow-match-e2e --format='{{.State.Health.Status}}' 2>/dev/null || echo "unknown")
            
            if [[ "$ingest_health" == "healthy" && "$extract_health" == "healthy" && "$match_health" == "healthy" ]]; then
                log_success "All services are healthy and ready"
                break
            fi
        fi
        
        log_info "Services are starting... ($elapsed/$timeout seconds)"
        sleep 5
        elapsed=$((elapsed + 5))
    done
    
    if [[ $elapsed -ge $timeout ]]; then
        log_error "Services failed to become healthy within $timeout seconds"
        log_info "Checking service status..."
        docker-compose -f docker-compose.e2e.yml ps
        exit 1
    fi
}

# Upload PDF and run pipeline
run_pipeline() {
    log_info "Starting pipeline demo with sample PDF..."
    
    # Upload the PDF
    log_info "Uploading PDF to ingest service..."
    
    upload_response=$(curl -s -X POST \
        -F "file=@$SAMPLE_PDF" \
        -F "metadata={\"po_numbers\":[\"PO-TEST-001\"],\"vendor_name\":\"Test Vendor Corp\",\"total_amount\":995.00}" \
        http://localhost:8003/api/v1/ingest/upload)
    
    if [[ $? -ne 0 ]]; then
        log_error "Failed to upload PDF"
        exit 1
    fi
    
    # Extract request ID
    if command -v jq &> /dev/null; then
        request_id=$(echo "$upload_response" | jq -r '.request_id')
        log_success "PDF uploaded successfully. Request ID: $request_id"
        echo "Upload response:"
        echo "$upload_response" | jq .
    else
        request_id=$(echo "$upload_response" | grep -o '"request_id":"[^"]*"' | cut -d'"' -f4)
        log_success "PDF uploaded successfully. Request ID: $request_id"
        echo "Upload response: $upload_response"
    fi
    
    if [[ -z "$request_id" || "$request_id" == "null" ]]; then
        log_error "Failed to extract request ID from upload response"
        exit 1
    fi
    
    # Poll for completion
    log_info "Polling for processing completion..."
    
    timeout=$DEMO_TIMEOUT
    elapsed=0
    poll_interval=5
    
    while [[ $elapsed -lt $timeout ]]; do
        status_response=$(curl -s "http://localhost:8003/api/v1/ingest/status/$request_id")
        
        if command -v jq &> /dev/null; then
            status=$(echo "$status_response" | jq -r '.status')
            processing_stage=$(echo "$status_response" | jq -r '.processing_stage // "unknown"')
        else
            status=$(echo "$status_response" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
            processing_stage="unknown"
        fi
        
        log_info "Status: $status, Stage: $processing_stage ($elapsed/$timeout seconds)"
        
        if [[ "$status" == "COMPLETED" ]]; then
            log_success "Processing completed successfully!"
            break
        elif [[ "$status" == "ERROR" ]]; then
            log_error "Processing failed!"
            if command -v jq &> /dev/null; then
                echo "$status_response" | jq .
            else
                echo "$status_response"
            fi
            exit 1
        fi
        
        sleep $poll_interval
        elapsed=$((elapsed + poll_interval))
    done
    
    if [[ $elapsed -ge $timeout ]]; then
        log_error "Processing did not complete within $timeout seconds"
        exit 1
    fi
    
    # Get final status and matching results
    log_info "Retrieving final processing results..."
    
    final_status=$(curl -s "http://localhost:8003/api/v1/ingest/status/$request_id")
    
    log_success "Final processing status:"
    if command -v jq &> /dev/null; then
        echo "$final_status" | jq .
    else
        echo "$final_status"
    fi
    
    # Try to get matching results from database
    log_info "Checking matching results in database..."
    
    # Connect to postgres and get matching results
    matching_result=$(docker exec invoiceflow-postgres-e2e psql -U testuser -d invoiceflow_test -t -c \
        "SELECT matched_status, matched_details FROM invoices WHERE request_id = '$request_id';" 2>/dev/null || echo "")
    
    if [[ -n "$matching_result" ]]; then
        log_success "Matching results from database:"
        echo "$matching_result"
    else
        log_warning "Could not retrieve matching results from database"
    fi
}

# Cleanup function
cleanup() {
    log_info "Cleaning up services..."
    cd "$PROJECT_ROOT"
    docker-compose -f docker-compose.e2e.yml down --remove-orphans
    docker-compose -f docker-compose.e2e.yml rm -f
    log_success "Cleanup completed"
}

# Show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --build-only     Only build Docker images, don't run the demo"
    echo "  --no-build       Skip building Docker images"
    echo "  --cleanup-only   Only cleanup existing containers"
    echo "  --help           Show this help message"
    echo ""
    echo "Prerequisites:"
    echo "  - Docker"
    echo "  - Docker Compose"
    echo "  - curl"
    echo "  - jq (optional, for formatted JSON output)"
}

# Main execution
main() {
    local build_only=false
    local no_build=false
    local cleanup_only=false
    
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --build-only)
                build_only=true
                shift
                ;;
            --no-build)
                no_build=true
                shift
                ;;
            --cleanup-only)
                cleanup_only=true
                shift
                ;;
            --help)
                show_usage
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
    
    # Trap for cleanup on exit
    trap cleanup EXIT
    
    log_info "🚀 Starting InvoiceFlow Pipeline Demo"
    echo "======================================="
    
    if [[ "$cleanup_only" == true ]]; then
        cleanup
        exit 0
    fi
    
    check_prerequisites
    create_sample_pdf
    
    if [[ "$no_build" != true ]]; then
        build_images
    fi
    
    if [[ "$build_only" == true ]]; then
        log_success "Build completed. Use --no-build to skip building in future runs."
        exit 0
    fi
    
    start_services
    run_pipeline
    
    echo ""
    log_success "🎉 Pipeline demo completed successfully!"
    echo "======================================="
    echo ""
    echo "The complete flow has been demonstrated:"
    echo "1. ✅ PDF uploaded to Ingest service"
    echo "2. ✅ File processed through Extraction service"
    echo "3. ✅ Invoice matched against Purchase Orders"
    echo "4. ✅ Results stored in database"
    echo ""
    echo "Services will be cleaned up automatically on exit."
    echo "To keep services running, press Ctrl+C to cancel cleanup."
    echo ""
    read -t 10 -p "Press Enter to cleanup now, or wait 10 seconds for auto-cleanup..."
}

# Run main function
main "$@" 