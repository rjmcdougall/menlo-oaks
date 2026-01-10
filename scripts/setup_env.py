#!/usr/bin/env python3
"""
Interactive setup script for UniFi Protect environment variables
Usage: python setup_env.py
"""

import os
import getpass
import sys

def get_input(prompt, default="", secret=False):
    """Get user input with optional default value"""
    if secret:
        if default:
            value = getpass.getpass(f"{prompt} [current value hidden]: ")
        else:
            value = getpass.getpass(f"{prompt}: ")
    else:
        if default:
            value = input(f"{prompt} [{default}]: ").strip()
        else:
            value = input(f"{prompt}: ").strip()
    
    return value if value else default

def main():
    """Main setup function"""
    print("🔧 UniFi Protect Environment Setup")
    print("=" * 50)
    print("This script will help you configure the environment variables needed")
    print("for the UniFi Protect license plate detection system.\n")
    
    # Check if .env file exists
    env_file = ".env.development"
    if os.path.exists(env_file):
        print(f"📁 Found existing {env_file}")
        overwrite = input("Do you want to update it? (y/N): ").strip().lower()
        if overwrite not in ['y', 'yes']:
            print("Setup cancelled.")
            return
        print()
    
    # Load existing values if file exists
    existing_vars = {}
    if os.path.exists(env_file):
        try:
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        existing_vars[key] = value
        except Exception as e:
            print(f"Warning: Could not read existing {env_file}: {e}")
    
    print("Please provide the following information:\n")
    
    # Collect configuration
    config = {}
    
    # Required settings
    print("📋 Required Settings:")
    config['GCP_PROJECT_ID'] = get_input(
        "Google Cloud Project ID", 
        existing_vars.get('GCP_PROJECT_ID', '')
    )
    
    print("\n🏠 UniFi Protect Connection:")
    config['UNIFI_PROTECT_HOST'] = get_input(
        "UniFi Protect hostname or IP", 
        existing_vars.get('UNIFI_PROTECT_HOST', '')
    )
    config['UNIFI_PROTECT_USERNAME'] = get_input(
        "UniFi Protect username", 
        existing_vars.get('UNIFI_PROTECT_USERNAME', '')
    )
    config['UNIFI_PROTECT_PASSWORD'] = get_input(
        "UniFi Protect password", 
        existing_vars.get('UNIFI_PROTECT_PASSWORD', ''),
        secret=True
    )
    
    # Optional settings with defaults
    print("\n⚙️  Optional Settings (press Enter for defaults):")
    config['UNIFI_PROTECT_PORT'] = get_input(
        "UniFi Protect port", 
        existing_vars.get('UNIFI_PROTECT_PORT', '443')
    )
    config['UNIFI_PROTECT_VERIFY_SSL'] = get_input(
        "Verify SSL certificates (true/false)", 
        existing_vars.get('UNIFI_PROTECT_VERIFY_SSL', 'true')
    )
    
    print("\n📊 BigQuery Settings:")
    config['BIGQUERY_DATASET'] = get_input(
        "BigQuery dataset name", 
        existing_vars.get('BIGQUERY_DATASET', 'license_plates')
    )
    config['BIGQUERY_TABLE'] = get_input(
        "BigQuery table name", 
        existing_vars.get('BIGQUERY_TABLE', 'detections')
    )
    config['BIGQUERY_LOCATION'] = get_input(
        "BigQuery location", 
        existing_vars.get('BIGQUERY_LOCATION', 'US')
    )
    
    print("\n🔐 Security Settings:")
    config['WEBHOOK_SECRET'] = get_input(
        "Webhook secret (recommended for security)", 
        existing_vars.get('WEBHOOK_SECRET', ''),
        secret=True
    )
    
    print("\n🎯 Processing Settings:")
    config['MIN_CONFIDENCE_THRESHOLD'] = get_input(
        "Minimum confidence threshold (0.0-1.0)", 
        existing_vars.get('MIN_CONFIDENCE_THRESHOLD', '0.7')
    )
    config['LOG_LEVEL'] = get_input(
        "Log level (DEBUG/INFO/WARNING/ERROR)", 
        existing_vars.get('LOG_LEVEL', 'INFO')
    )
    
    # Optional image storage
    store_images = get_input(
        "Store detection images? (true/false)", 
        existing_vars.get('STORE_IMAGES', 'false')
    )
    config['STORE_IMAGES'] = store_images
    
    if store_images.lower() == 'true':
        config['GCS_BUCKET_NAME'] = get_input(
            "Google Cloud Storage bucket name for images", 
            existing_vars.get('GCS_BUCKET_NAME', '')
        )
    else:
        config['GCS_BUCKET_NAME'] = existing_vars.get('GCS_BUCKET_NAME', '')
    
    # Set environment type
    config['ENVIRONMENT'] = 'development'
    
    # Validate required fields
    required_fields = ['GCP_PROJECT_ID', 'UNIFI_PROTECT_HOST', 'UNIFI_PROTECT_USERNAME', 'UNIFI_PROTECT_PASSWORD']
    missing_fields = [field for field in required_fields if not config.get(field)]
    
    if missing_fields:
        print(f"\n❌ Missing required fields: {', '.join(missing_fields)}")
        print("Setup incomplete. Please provide all required information.")
        return
    
    # Write configuration file
    try:
        with open(env_file, 'w') as f:
            f.write("# UniFi Protect License Plate Detection Configuration\n")
            f.write(f"# Generated on {os.popen('date').read().strip()}\n\n")
            
            f.write("# Required Settings\n")
            f.write(f"GCP_PROJECT_ID={config['GCP_PROJECT_ID']}\n\n")
            
            f.write("# UniFi Protect Connection\n")
            f.write(f"UNIFI_PROTECT_HOST={config['UNIFI_PROTECT_HOST']}\n")
            f.write(f"UNIFI_PROTECT_PORT={config['UNIFI_PROTECT_PORT']}\n")
            f.write(f"UNIFI_PROTECT_USERNAME={config['UNIFI_PROTECT_USERNAME']}\n")
            f.write(f"UNIFI_PROTECT_PASSWORD={config['UNIFI_PROTECT_PASSWORD']}\n")
            f.write(f"UNIFI_PROTECT_VERIFY_SSL={config['UNIFI_PROTECT_VERIFY_SSL']}\n\n")
            
            f.write("# BigQuery Configuration\n")
            f.write(f"BIGQUERY_DATASET={config['BIGQUERY_DATASET']}\n")
            f.write(f"BIGQUERY_TABLE={config['BIGQUERY_TABLE']}\n")
            f.write(f"BIGQUERY_LOCATION={config['BIGQUERY_LOCATION']}\n\n")
            
            f.write("# Security\n")
            if config['WEBHOOK_SECRET']:
                f.write(f"WEBHOOK_SECRET={config['WEBHOOK_SECRET']}\n")
            f.write("\n")
            
            f.write("# Processing Configuration\n")
            f.write(f"MIN_CONFIDENCE_THRESHOLD={config['MIN_CONFIDENCE_THRESHOLD']}\n")
            f.write(f"STORE_IMAGES={config['STORE_IMAGES']}\n")
            if config['GCS_BUCKET_NAME']:
                f.write(f"GCS_BUCKET_NAME={config['GCS_BUCKET_NAME']}\n")
            f.write("\n")
            
            f.write("# Logging\n")
            f.write(f"LOG_LEVEL={config['LOG_LEVEL']}\n\n")
            
            f.write("# Environment\n")
            f.write(f"ENVIRONMENT={config['ENVIRONMENT']}\n")
        
        print(f"\n✅ Configuration saved to {env_file}")
        print("\nNext steps:")
        print("1. Test your connection:")
        print("   python test_unifi_cli.py test")
        print("2. List your cameras:")
        print("   python test_unifi_cli.py cameras")
        print("3. Check for recent events:")
        print("   python test_unifi_cli.py events")
        print("4. Look for license plate detections:")
        print("   python test_unifi_cli.py plates")
        
    except Exception as e:
        print(f"\n❌ Failed to write configuration file: {e}")
        return
    
    # Offer to export environment variables for current session
    print(f"\n💡 To use these settings in your current terminal session, run:")
    print(f"   export $(cat {env_file} | grep -v '^#' | xargs)")
    
    export_now = input("\nDo you want to export these variables now? (y/N): ").strip().lower()
    if export_now in ['y', 'yes']:
        # Export variables to current environment
        for key, value in config.items():
            if value:  # Only export non-empty values
                os.environ[key] = value
        print("✅ Environment variables exported for this session!")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Setup cancelled by user")
    except Exception as e:
        print(f"\n❌ Setup failed: {e}")
        sys.exit(1)
