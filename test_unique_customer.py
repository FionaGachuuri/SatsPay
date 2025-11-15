#!/usr/bin/env python3
"""
Quick test to create a unique customer
"""

import os
import sys
import logging
import uuid
from dotenv import load_dotenv

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.bitnob_service import BitnobService

# Load environment variables
load_dotenv()

# Set up minimal logging
logging.basicConfig(level=logging.INFO)

def main():
    # Get configuration
    api_key = os.getenv('BITNOB_API_KEY')
    secret_key = os.getenv('BITNOB_SECRET_KEY')
    base_url = os.getenv('BITNOB_BASE_URL', 'https://sandboxapi.bitnob.co')
    
    if not api_key or not secret_key:
        print("❌ ERROR: BITNOB_API_KEY and BITNOB_SECRET_KEY must be set")
        return
    
    # Initialize service
    bitnob_service = BitnobService(api_key, secret_key, base_url)
    
    # Create unique customer data
    unique_id = str(uuid.uuid4())[:8]
    test_customer_data = {
        'full_name': f'Test User {unique_id}',
        'email': f'test{unique_id}@example.com',
        'phone_number': f'+123456{unique_id[:4]}'
    }
    
    print(f"Creating unique customer: {test_customer_data}")
    customer_result = bitnob_service.create_customer(
        test_customer_data['full_name'],
        test_customer_data['email'],
        test_customer_data['phone_number']
    )
    
    if customer_result.get('error'):
        print(f"❌ Customer creation failed: {customer_result.get('message')}")
    else:
        print(f"✅ Customer creation successful!")
        print(f"Customer ID: {customer_result.get('data', {}).get('id')}")

if __name__ == '__main__':
    main()
