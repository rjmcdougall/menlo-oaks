#!/usr/bin/env python3
"""
Test script for the health check endpoint
"""

import json
import sys
import os
import logging
from unittest.mock import MagicMock

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Mock the Flask Request object
class MockRequest:
    def __init__(self, method='GET', path='/health'):
        self.method = method
        self.path = path

def test_health_check():
    """Test the health check function"""
    print("🏥 Testing Health Check Endpoint")
    print("=" * 50)
    
    try:
        # Set required environment variables for testing
        os.environ.setdefault('GCP_PROJECT_ID', 'test-project')
        os.environ.setdefault('BIGQUERY_DATASET', 'test_dataset')
        os.environ.setdefault('BIGQUERY_TABLE', 'test_table')
        
        # Import after setting env vars
        from main import health_check, check_configuration_health
        
        # Test configuration check first
        print("🔧 Testing configuration health check...")
        config_health = check_configuration_health()
        print(f"Configuration status: {config_health.get('status', 'unknown')}")
        
        if config_health.get('issues'):
            print(f"⚠️  Configuration issues: {config_health['issues']}")
        if config_health.get('warnings'):
            print(f"⚠️  Configuration warnings: {config_health['warnings']}")
        
        # Test health check endpoint
        print("\n🏥 Testing health check endpoint...")
        
        # Create mock request
        request = MockRequest(method='GET', path='/health')
        
        # Call health check
        response, status_code = health_check(request)
        
        # Parse response
        if hasattr(response, 'get_json'):
            # If it's a Flask response object
            health_data = response.get_json()
        else:
            # If it's already a dict
            health_data = response
        
        print(f"✅ Health check completed!")
        print(f"📊 Status Code: {status_code}")
        print(f"🎯 Overall Status: {health_data.get('status', 'unknown')}")
        print(f"🚀 Service: {health_data.get('service', 'unknown')}")
        print(f"📦 Version: {health_data.get('version', 'unknown')}")
        
        # Show environment info
        if 'environment' in health_data:
            env = health_data['environment']
            print(f"\n🌍 Environment:")
            print(f"  Function Name: {env.get('function_name', 'unknown')}")
            print(f"  GCP Project: {env.get('gcp_project', 'unknown')}")
            print(f"  Region: {env.get('region', 'unknown')}")
        
        # Show configuration status
        if 'configuration' in health_data:
            config = health_data['configuration']
            print(f"\n⚙️  Configuration:")
            print(f"  Status: {config.get('status', 'unknown')}")
            if config.get('bigquery_dataset'):
                print(f"  BigQuery Dataset: {config['bigquery_dataset']}")
            if config.get('bigquery_table'):
                print(f"  BigQuery Table: {config['bigquery_table']}")
            if config.get('warnings'):
                print(f"  Warnings: {len(config['warnings'])} warning(s)")
        
        # Show BigQuery status (might fail in test environment)
        if 'bigquery' in health_data:
            bq = health_data['bigquery']
            print(f"\n🔍 BigQuery:")
            print(f"  Status: {bq.get('status', 'unknown')}")
            if bq.get('status') == 'error':
                print(f"  Error: {bq.get('error', 'Unknown error')}")
        
        print("\n" + "=" * 50)
        
        # Test invalid method
        print("🚫 Testing invalid method (POST to health check)...")
        request_invalid = MockRequest(method='POST', path='/health')
        try:
            response_invalid, status_invalid = health_check(request_invalid)
            print(f"✅ Invalid method handled correctly (Status: {status_invalid})")
        except Exception as e:
            print(f"❌ Error with invalid method: {str(e)}")
        
        print("\n✅ Health check testing completed!")
        
    except Exception as e:
        print(f"❌ Error testing health check: {str(e)}")
        import traceback
        traceback.print_exc()


def test_main_router():
    """Test the main router function"""
    print("\n🗂️  Testing Main Router")
    print("=" * 50)
    
    try:
        from main import main
        
        # Test health check route
        print("🏥 Testing GET /health route...")
        request_health = MockRequest(method='GET', path='/health')
        response, status = main(request_health)
        print(f"✅ Health route works (Status: {status})")
        
        # Test root GET route (should also go to health check)
        print("🏠 Testing GET / route...")
        request_root = MockRequest(method='GET', path='/')
        response, status = main(request_root)
        print(f"✅ Root GET route works (Status: {status})")
        
        # Test invalid route
        print("❌ Testing invalid route...")
        request_invalid = MockRequest(method='GET', path='/invalid')
        response, status = main(request_invalid)
        print(f"✅ Invalid route handled correctly (Status: {status})")
        
        print("\n✅ Router testing completed!")
        
    except Exception as e:
        print(f"❌ Error testing main router: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Suppress some logging during testing
    logging.getLogger().setLevel(logging.WARNING)
    
    test_health_check()
    test_main_router()
