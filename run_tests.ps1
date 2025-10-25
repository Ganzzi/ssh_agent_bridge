#!/bin/bash/powershell
# Test runner script for SSH Agent Bridge
# This script provides a safe way to run tests individually without hanging

Write-Host "SSH Agent Bridge Test Runner" -ForegroundColor Green
Write-Host "===========================" -ForegroundColor Green
Write-Host ""
Write-Host "Available Test Commands:" -ForegroundColor Cyan
Write-Host ""
Write-Host "Fast Unit Tests (no async I/O):" -ForegroundColor Yellow
Write-Host "  uv run pytest tests/test_core.py -m fast -v" -ForegroundColor White
Write-Host ""
Write-Host "Individual Test Classes:" -ForegroundColor Yellow
Write-Host "  uv run pytest tests/test_core.py::TestDataTypes -v" -ForegroundColor White
Write-Host "  uv run pytest tests/test_core.py::TestExceptions -v" -ForegroundColor White
Write-Host "  uv run pytest tests/test_core.py::TestSSHService -v" -ForegroundColor White
Write-Host ""
Write-Host "Individual Tests:" -ForegroundColor Yellow
Write-Host "  uv run pytest tests/test_core.py::TestSSHService::test_service_initialization -v" -ForegroundColor White
Write-Host "  uv run pytest tests/test_core.py::TestSSHService::test_marker_generation -v" -ForegroundColor White
Write-Host ""
Write-Host "Connection Management Tests:" -ForegroundColor Yellow
Write-Host "  uv run pytest tests/test_core.py::TestConnectionManagement::test_connection_creation_success -v" -ForegroundColor White
Write-Host ""
Write-Host "Coverage Report:" -ForegroundColor Yellow
Write-Host "  uv run pytest tests/test_core.py::TestDataTypes tests/test_core.py::TestExceptions --cov=src/ssh_agent_bridge --cov-report=html" -ForegroundColor White
Write-Host ""
Write-Host "NOTE: Avoid running 'uv run pytest tests/test_core.py' without filters!" -ForegroundColor Red
Write-Host "      It may hang due to asyncio fixture issues." -ForegroundColor Red
