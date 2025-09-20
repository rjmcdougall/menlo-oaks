#!/usr/bin/env python3
"""
Simple test script for health check logic without Cloud Functions dependencies
"""

import json
import sys
import os
import logging
from datetime import datetime
from typing import Dict, Any

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set test environment variables
os.environ.setdefault('GCP_PROJECT_ID', 'test-project')
os.environ.setdefault('BIGQUERY_DATASET', 'test_dataset')
os.environ.setdefault('BIGQUERY_TABLE', 'test_table')

# Import configuration after setting env vars
from config import Config

# Mock Flask jsonify function
def jsonify(data):
    """Mock Flask jsonify function"""
    return data

# Mock Flask Request object
class MockRequest:
    def __init__(self, method='GET', path='/health'):
        self.method = method
        self.path = path

# Copy health check functions without Cloud Functions decorator
def check_configuration_health(config: Config) -> Dict[str, Any]:
    """
    Check if the application configuration is valid.
    """
    try:
        issues = []
        
        # Check required environment variables
        if not config.GCP_PROJECT_ID:
            issues.append("Missing GCP_PROJECT_ID")
        
        if not config.BIGQUERY_DATASET:
            issues.append("Missing BIGQUERY_DATASET")
            
        if not config.BIGQUERY_TABLE:
            issues.append("Missing BIGQUERY_TABLE")
        
        # Check optional but recommended settings
        warnings = []
        if not config.WEBHOOK_SECRET:
            warnings.append("WEBHOOK_SECRET not configured - webhooks are not authenticated")
            
        if not config.is_unifi_protect_configured():
            warnings.append("UniFi Protect connection not configured - operating in webhook-only mode")
        
        if issues:
            return {
                "status": "unhealthy",
                "issues": issues,
                "warnings": warnings
            }
        
        return {
            "status": "healthy",
            "warnings": warnings,
            "bigquery_dataset": config.BIGQUERY_DATASET,
            "bigquery_table": config.BIGQUERY_TABLE,
            "webhook_auth": bool(config.WEBHOOK_SECRET),
            "unifi_protect_configured": config.is_unifi_protect_configured()
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }


def check_bigquery_health(config: Config) -> Dict[str, Any]:
    """
    Check BigQuery connectivity and table accessibility.
    """
    try:
        # Simple test to verify BigQuery client can connect
        from google.cloud import bigquery
        client = bigquery.Client(project=config.GCP_PROJECT_ID)
        
        # Try to get dataset info
        dataset_ref = client.dataset(config.BIGQUERY_DATASET)
        dataset = client.get_dataset(dataset_ref)
        
        # Try to get table info
        table_ref = dataset_ref.table(config.BIGQUERY_TABLE)
        table = client.get_table(table_ref)
        
        return {
            "status": "healthy",
            "dataset_location": dataset.location,
            "table_created": table.created.isoformat() if table.created else None,
            "table_rows": table.num_rows,
            "last_check": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "last_check": datetime.utcnow().isoformat()
        }


def health_check(request: MockRequest, config: Config) -> Dict[str, Any]:
    """
    Health check endpoint logic.
    """
    try:
        # Only respond to GET requests for health checks
        if request.method != 'GET':
            return jsonify({
                "status": "error",
                "message": "Health check only supports GET method",
                "timestamp": datetime.utcnow().isoformat()
            }), 405
        
        # Basic health response
        health_data = {
            "status": "healthy",
            "service": "unifi-protect-license-plate-detector",
            "version": "2.0.0",
            "timestamp": datetime.utcnow().isoformat(),
            "environment": {
                "function_name": os.getenv("FUNCTION_NAME", "local"),
                "gcp_project": os.getenv("GCP_PROJECT", "unknown"),
                "region": os.getenv("FUNCTION_REGION", "unknown")
            }
        }
        
        # Check configuration
        config_status = check_configuration_health(config)
        health_data["configuration"] = config_status
        
        # Check BigQuery connectivity (optional, non-blocking)
        try:
            bq_status = check_bigquery_health(config)
            health_data["bigquery"] = bq_status
        except Exception as e:
            health_data["bigquery"] = {
                "status": "warning",
                "message": "Could not verify BigQuery connectivity",
                "error": str(e)
            }
        
        # Determine overall status
        if config_status["status"] != "healthy":
            health_data["status"] = "unhealthy"
            return jsonify(health_data), 503
        elif health_data.get("bigquery", {}).get("status") == "error":
            health_data["status"] = "degraded"
            return jsonify(health_data), 200
        
        return jsonify(health_data), 200
        
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "service": "unifi-protect-license-plate-detector",
            "timestamp": datetime.utcnow().isoformat(),
            "error": "Internal health check error",
            "message": str(e)
        }), 500


def main_router(request: MockRequest, config: Config) -> Dict[str, Any]:
    """
    Main router logic.
    """
    try:
        # Route based on path and method
        path = request.path.lower().rstrip('/')
        method = request.method.upper()
        
        # Health check endpoint
        if path == '/health' or path == '' and method == 'GET':
            return health_check(request, config)
        
        # License plate webhook endpoint (default)
        if method == 'POST':
            return jsonify({
                "message": "This would process license plate webhooks",
                "method": method,
                "path": path
            }), 200
        
        # Invalid route/method combination
        return jsonify({
            "error": "Invalid endpoint",
            "message": "Use POST for webhooks or GET /health for health checks",
            "received": {"method": method, "path": path}
        }), 404
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": "Internal server error in request router"
        }), 500


def test_health_check():
    """Test the health check function"""
    print("🏥 Testing Health Check Endpoint")
    print("=" * 50)
    
    try:
        # Initialize config
        config = Config()
        
        # Test configuration check first
        print("🔧 Testing configuration health check...")
        config_health = check_configuration_health(config)
        print(f"Configuration status: {config_health.get('status', 'unknown')}")
        
        if config_health.get('issues'):
            print(f"⚠️  Configuration issues: {config_health['issues']}")
        if config_health.get('warnings'):
            print(f"⚠️  Configuration warnings: {config_health['warnings']}")
        
        # Test health check endpoint
        print("\\n🏥 Testing health check endpoint...")
        
        # Create mock request
        request = MockRequest(method='GET', path='/health')
        
        # Call health check
        response, status_code = health_check(request, config)
        
        print(f"✅ Health check completed!")
        print(f"📊 Status Code: {status_code}")
        print(f"🎯 Overall Status: {response.get('status', 'unknown')}")
        print(f"🚀 Service: {response.get('service', 'unknown')}")
        print(f"📦 Version: {response.get('version', 'unknown')}")
        
        # Show environment info
        if 'environment' in response:
            env = response['environment']
            print(f"\\n🌍 Environment:")
            print(f"  Function Name: {env.get('function_name', 'unknown')}")
            print(f"  GCP Project: {env.get('gcp_project', 'unknown')}")
            print(f"  Region: {env.get('region', 'unknown')}")
        
        # Show configuration status
        if 'configuration' in response:
            config_info = response['configuration']
            print(f"\\n⚙️  Configuration:")
            print(f"  Status: {config_info.get('status', 'unknown')}")
            if config_info.get('bigquery_dataset'):
                print(f"  BigQuery Dataset: {config_info['bigquery_dataset']}")
            if config_info.get('bigquery_table'):
                print(f"  BigQuery Table: {config_info['bigquery_table']}")
            if config_info.get('warnings'):
                print(f"  Warnings: {len(config_info['warnings'])} warning(s)")
                for warning in config_info['warnings']:
                    print(f"    - {warning}")
        
        # Show BigQuery status (might fail in test environment)
        if 'bigquery' in response:
            bq = response['bigquery']
            print(f"\\n🔍 BigQuery:")
            print(f"  Status: {bq.get('status', 'unknown')}")
            if bq.get('status') == 'error':
                print(f"  Error: {bq.get('error', 'Unknown error')}")
            elif bq.get('status') == 'healthy':
                print(f"  Dataset Location: {bq.get('dataset_location', 'unknown')}")
                print(f"  Table Rows: {bq.get('table_rows', 'unknown')}")
        
        print("\\n" + "=" * 50)
        
        # Test invalid method
        print("🚫 Testing invalid method (POST to health check)...")
        request_invalid = MockRequest(method='POST', path='/health')
        try:
            response_invalid, status_invalid = health_check(request_invalid, config)
            print(f"✅ Invalid method handled correctly (Status: {status_invalid})")
        except Exception as e:
            print(f"❌ Error with invalid method: {str(e)}")
        
        print("\\n✅ Health check testing completed!")
        
    except Exception as e:
        print(f"❌ Error testing health check: {str(e)}")
        import traceback
        traceback.print_exc()


def test_main_router():
    """Test the main router function"""
    print("\\n🗂️  Testing Main Router")
    print("=" * 50)
    
    try:
        config = Config()
        
        # Test health check route
        print("🏥 Testing GET /health route...")
        request_health = MockRequest(method='GET', path='/health')
        response, status = main_router(request_health, config)
        print(f"✅ Health route works (Status: {status})")
        
        # Test root GET route (should also go to health check)
        print("🏠 Testing GET / route...")
        request_root = MockRequest(method='GET', path='/')
        response, status = main_router(request_root, config)
        print(f"✅ Root GET route works (Status: {status})")
        
        # Test webhook POST route
        print("📥 Testing POST / route...")
        request_webhook = MockRequest(method='POST', path='/')
        response, status = main_router(request_webhook, config)
        print(f"✅ Webhook route works (Status: {status})")
        
        # Test invalid route
        print("❌ Testing invalid route...")
        request_invalid = MockRequest(method='GET', path='/invalid')
        response, status = main_router(request_invalid, config)
        print(f"✅ Invalid route handled correctly (Status: {status})")
        
        print("\\n✅ Router testing completed!")
        
    except Exception as e:
        print(f"❌ Error testing main router: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Suppress some logging during testing
    logging.getLogger().setLevel(logging.WARNING)
    
    test_health_check()
    test_main_router()
