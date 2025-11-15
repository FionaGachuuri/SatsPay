#!/usr/bin/env python3
"""
Test script for Bitnob API connection
This script will help debug the API endpoint issues
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.bitnob_service import BitnobService

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def main():
    print("=== Bitnob API Connection Test ===\n")
    
    # Get configuration
    api_key = os.getenv('BITNOB_API_KEY')
    secret_key = os.getenv('BITNOB_SECRET_KEY')
    base_url = os.getenv('BITNOB_BASE_URL', 'https://sandboxapi.bitnob.co')
    
    print(f"API Key: {'***' + api_key[-4:] if api_key else 'NOT SET'}")
    print(f"Secret Key: {'***' + secret_key[-4:] if secret_key else 'NOT SET'}")
    print(f"Base URL: {base_url}")
    print()
    
    if not api_key or not secret_key:
        print("❌ ERROR: BITNOB_API_KEY and BITNOB_SECRET_KEY must be set")
        return
    
    # Initialize service
    bitnob_service = BitnobService(api_key, secret_key, base_url)
    
    # Test API connection
    print("Testing API connection...")
    test_results = bitnob_service.test_api_connection()
    
    print("\n=== Test Results ===")
    for endpoint, result in test_results.items():
        status = "✅ SUCCESS" if result['success'] else "❌ FAILED"
        print(f"{status}: {endpoint}")
        if not result['success'] and 'error' in result:
            print(f"   Error: {result['error']}")
    
    # Test customer creation with different data formats
    print("\n=== Testing Customer Creation ===")
    test_customer_data = {
        'full_name': 'Test User',
        'email': 'test@example.com',
        'phone_number': '+1234567890'
    }
    
    print(f"Attempting to create customer: {test_customer_data}")
    customer_result = bitnob_service.create_customer(
        test_customer_data['full_name'],
        test_customer_data['email'],
        test_customer_data['phone_number']
    )
    
    if customer_result.get('error'):
        print(f"❌ Customer creation failed: {customer_result.get('message')}")
    else:
        print(f"✅ Customer creation successful: {customer_result}")

if __name__ == '__main__':
    main()
