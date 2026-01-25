#!/bin/bash
# Docker management script for DOI and Reference Checker

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

function print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

function print_error() {
    echo -e "${RED}✗ $1${NC}"
}

function print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

function show_usage() {
    echo "DOI and Reference Checker - Docker Management"
    echo ""
    echo "Usage: $0 {start|stop|restart|status|logs|build|clean}"
    echo ""
    echo "Commands:"
    echo "  start    - Start the application"
    echo "  stop     - Stop the application"
    echo "  restart  - Restart the application"
    echo "  status   - Show application status"
    echo "  logs     - View application logs"
    echo "  build    - Rebuild the Docker image"
    echo "  clean    - Stop and remove containers, images, and volumes"
    echo ""
}

function check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed"
        exit 1
    fi

    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is not installed"
        exit 1
    fi
}

function start_app() {
    print_info "Starting DOI and Reference Checker..."
    docker-compose up -d

    sleep 3

    if check_health; then
        print_success "Application started successfully"
        print_info "Access the web interface at: http://localhost:5003"
    else
        print_error "Application failed to start properly"
        print_info "Check logs with: $0 logs"
        exit 1
    fi
}

function stop_app() {
    print_info "Stopping DOI and Reference Checker..."
    docker-compose down
    print_success "Application stopped"
}

function restart_app() {
    print_info "Restarting DOI and Reference Checker..."
    docker-compose restart

    sleep 3

    if check_health; then
        print_success "Application restarted successfully"
    else
        print_error "Application failed to restart properly"
        exit 1
    fi
}

function show_status() {
    print_info "Application Status:"
    docker-compose ps

    echo ""
    print_info "Health Check:"
    if check_health; then
        print_success "Application is healthy"
    else
        print_error "Application is not responding"
    fi
}

function show_logs() {
    print_info "Showing logs (Press Ctrl+C to exit)..."
    docker-compose logs -f
}

function build_app() {
    print_info "Building Docker image..."
    docker-compose build --no-cache
    print_success "Build complete"
}

function clean_app() {
    print_info "This will remove all containers, images, and volumes"
    read -p "Are you sure? (yes/no): " confirm

    if [ "$confirm" != "yes" ]; then
        print_info "Operation cancelled"
        exit 0
    fi

    print_info "Stopping containers..."
    docker-compose down -v

    print_info "Removing Docker image..."
    docker rmi doi-checker 2>/dev/null || true

    print_info "Cleaning build cache..."
    docker builder prune -f

    print_success "Cleanup complete"
}

function check_health() {
    response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5003/api/status 2>/dev/null || echo "000")

    if [ "$response" = "200" ]; then
        return 0
    else
        return 1
    fi
}

# Main script
check_docker

case "${1:-}" in
    start)
        start_app
        ;;
    stop)
        stop_app
        ;;
    restart)
        restart_app
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    build)
        build_app
        ;;
    clean)
        clean_app
        ;;
    *)
        show_usage
        exit 1
        ;;
esac
