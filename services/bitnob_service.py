import requests
import hmac
import hashlib
import json
import time
from datetime import datetime
from typing import Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)

class BitnobService:
    def __init__(self, api_key: str, secret_key: str, base_url: str):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        
        # Set default headers
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
    
    def _generate_signature(self, timestamp: str, method: str, path: str, body: str = '') -> str:
        """Generate HMAC signature for Bitnob API"""
        message = f"{timestamp}{method.upper()}{path}{body}"
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """Make authenticated request to Bitnob API"""
        url = f"{self.base_url}{endpoint}"
        timestamp = str(int(time.time()))
        body = json.dumps(data) if data else ''
        
        # Generate signature
        signature = self._generate_signature(timestamp, method, endpoint, body)
        
        # Set authentication headers
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'X-Timestamp': timestamp,
            'X-Signature': signature
        }
        
        # Add debug logging
        logger.debug(f"Making {method} request to: {url}")
        if body:
            logger.debug(f"Request body: {body}")
        
        try:
            if method.upper() == 'GET':
                response = self.session.get(url, headers=headers, params=data)
            elif method.upper() == 'POST':
                # Ensure content-type is set correctly for JSON
                if body:
                    headers['Content-Type'] = 'application/json'
                response = self.session.post(url, headers=headers, json=data if data else None)
            elif method.upper() == 'PUT':
                if body:
                    headers['Content-Type'] = 'application/json'
                response = self.session.put(url, headers=headers, json=data if data else None)
            elif method.upper() == 'DELETE':
                response = self.session.delete(url, headers=headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            logger.debug(f"Response status: {response.status_code}")
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Bitnob API request failed: {e}")
            
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    logger.error(f"Error response: {error_data}")
                    return {'error': True, 'message': error_data.get('message', str(e))}
                except:
                    logger.error(f"Raw response content: {e.response.text}")
                    pass
            return {'error': True, 'message': str(e)}
    
    def create_customer(self, full_name: str, email: str, phone_number: str) -> Dict[str, Any]:
        """Create a new customer account"""
        data = {
            'firstName': full_name.split()[0] if full_name else '',
            'lastName': ' '.join(full_name.split()[1:]) if len(full_name.split()) > 1 else '',
            'email': email,
            'phoneNumber': phone_number,
            'type': 'individual'
        }
        
        logger.info(f"Creating Bitnob customer for {phone_number}")
        
        # Use the correct API endpoint
        result = self._make_request('POST', '/api/v1/customers', data)
        
        if not result.get('error'):
            logger.info(f"Customer created successfully: {result.get('data', {}).get('id')}")
        else:
            logger.error(f"Failed to create customer: {result.get('message')}")
        
        return result
    
    def get_bitcoin_wallet(self) -> Dict[str, Any]:
        """Get the company's Bitcoin wallet (wallets are at company level, not customer level)"""
        logger.info("Getting company Bitcoin wallet")
        
        result = self._make_request('GET', '/api/v1/wallets')
        
        if result.get('error'):
            logger.error(f"Failed to get wallets: {result.get('message')}")
            return result
        
        # Find the Bitcoin wallet
        wallets = result.get('data', [])
        bitcoin_wallet = None
        
        for wallet in wallets:
            if wallet.get('currency', '').lower() == 'btc' or wallet.get('type') == 'bitcoin':
                bitcoin_wallet = wallet
                break
        
        if bitcoin_wallet:
            logger.info(f"Found Bitcoin wallet: {bitcoin_wallet['id']}")
            return {
                'error': False,
                'data': bitcoin_wallet
            }
        else:
            logger.error("No Bitcoin wallet found")
            return {
                'error': True,
                'message': 'No Bitcoin wallet found for this company'
            }
    
    def get_wallet_balance(self, wallet_id: str) -> Dict[str, Any]:
        """Get wallet balance"""
        logger.info(f"Getting balance for wallet {wallet_id}")
        
        # Get all wallets and find the specified one
        wallets_result = self._make_request('GET', '/api/v1/wallets')
        
        if wallets_result.get('error'):
            logger.error(f"Failed to get wallets: {wallets_result.get('message')}")
            return wallets_result
        
        # Find the specific wallet
        wallets = wallets_result.get('data', [])
        for wallet in wallets:
            if wallet.get('id') == wallet_id:
                logger.info(f"Balance retrieved successfully for wallet {wallet_id}")
                return {
                    'error': False,
                    'data': {
                        'balance': wallet.get('balance', {}),
                        'currency': wallet.get('currency'),
                        'wallet_id': wallet_id
                    }
                }
        
        logger.error(f"Wallet {wallet_id} not found")
        return {
            'error': True,
            'message': f'Wallet {wallet_id} not found'
        }
    
    def generate_customer_address(self, customer_email: str) -> Dict[str, Any]:
        """Generate a Bitcoin address for a customer"""
        logger.info(f"Generating Bitcoin address for customer {customer_email}")
        
        data = {
            'customerEmail': customer_email
        }
        
        result = self._make_request('POST', '/api/v1/addresses/generate', data)
        
        if not result.get('error'):
            logger.info(f"Address generated successfully: {result.get('data', {}).get('address')}")
        else:
            logger.error(f"Failed to generate address: {result.get('message')}")
        
        return result
    
    def send_bitcoin(self, wallet_id: str, recipient_address: str, amount: float, description: str = '') -> Dict[str, Any]:
        """Send Bitcoin to an address"""
        data = {
            'walletId': wallet_id,
            'address': recipient_address,
            'amount': str(amount),
            'currency': 'BTC',
            'description': description
        }
        
        logger.info(f"Sending {amount} BTC from wallet {wallet_id} to {recipient_address}")
        result = self._make_request('POST', '/api/v1/transactions/send', data)
        
        if not result.get('error'):
            logger.info(f"Transaction initiated successfully: {result.get('data', {}).get('id')}")
        else:
            logger.error(f"Failed to send Bitcoin: {result.get('message')}")
        
        return result
    
    def get_transaction(self, transaction_id: str) -> Dict[str, Any]:
        """Get transaction details"""
        logger.info(f"Getting transaction details for {transaction_id}")
        result = self._make_request('GET', f'/api/v1/transactions/{transaction_id}')
        
        if result.get('error'):
            logger.error(f"Failed to get transaction: {result.get('message')}")
        
        return result
    
    def get_wallet_transactions(self, wallet_id: str, limit: int = 10) -> Dict[str, Any]:
        """Get wallet transaction history"""
        params = {
            'limit': limit,
            'walletId': wallet_id
        }
        
        logger.info(f"Getting transactions for wallet {wallet_id}")
        result = self._make_request('GET', '/api/v1/transactions', params)
        
        if result.get('error'):
            logger.error(f"Failed to get wallet transactions: {result.get('message')}")
        
        return result
    
    def validate_bitcoin_address(self, address: str) -> Dict[str, Any]:
        """Validate Bitcoin address"""
        data = {
            'address': address,
            'currency': 'BTC'
        }
        
        logger.info(f"Validating Bitcoin address: {address}")
        result = self._make_request('POST', '/api/v1/addresses/validate', data)
        
        if result.get('error'):
            logger.error(f"Failed to validate address: {result.get('message')}")
        
        return result
    
    def estimate_fee(self, amount: float) -> Dict[str, Any]:
        """Estimate transaction fee"""
        data = {
            'amount': str(amount),
            'currency': 'BTC'
        }
        
        logger.info(f"Estimating fee for {amount} BTC")
        result = self._make_request('POST', '/api/v1/transactions/estimate-fee', data)
        
        if result.get('error'):
            logger.error(f"Failed to estimate fee: {result.get('message')}")
        
        return result
    
    def get_btc_rate(self, currency: str = 'USD') -> Dict[str, Any]:
        """Get current BTC exchange rate"""
        params = {
            'from': 'BTC',
            'to': currency
        }
        
        logger.info(f"Getting BTC to {currency} exchange rate")
        result = self._make_request('GET', '/api/v1/rates', params)
        
        if result.get('error'):
            logger.error(f"Failed to get exchange rate: {result.get('message')}")
        
        return result
    
    def verify_webhook(self, payload: str, signature: str) -> bool:
        """Verify webhook signature"""
        try:
            expected_signature = hmac.new(
                self.secret_key.encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(signature, expected_signature)
        except Exception as e:
            logger.error(f"Webhook verification failed: {e}")
            return False

    def test_api_connection(self) -> Dict[str, Any]:
        """Test API connection and available endpoints"""
        logger.info("Testing Bitnob API connection")
        
        # Test endpoints that might exist
        test_endpoints = [
            ('GET', '/api/v1/status'),
            ('GET', '/v1/status'),
            ('GET', '/status'),
            ('GET', '/health'),
            ('GET', '/api/health'),
            ('GET', '/api/v1/health'),
            ('GET', '/'),
            ('GET', '/api/v1/rates'),
            ('GET', '/rates')
        ]
        
        results = {}
        for method, endpoint in test_endpoints:
            try:
                logger.info(f"Testing {method} {endpoint}")
                result = self._make_request(method, endpoint)
                results[endpoint] = {
                    'success': not result.get('error', False),
                    'response': result
                }
                if not result.get('error'):
                    logger.info(f"SUCCESS: {endpoint} is accessible")
                    break  # Found a working endpoint
            except Exception as e:
                results[endpoint] = {
                    'success': False,
                    'error': str(e)
                }
                logger.warning(f"FAILED: {endpoint} - {e}")
        
        return results

# Utility functions for common operations
def create_bitnob_account(bitnob_service: BitnobService, full_name: str, email: str, phone_number: str) -> Optional[Dict]:
    """Complete account creation flow"""
    try:
        # Create customer
        customer_result = bitnob_service.create_customer(full_name, email, phone_number)
        if customer_result.get('error'):
            return None
        
        customer_id = customer_result['data']['id']
        
        # Get the company's Bitcoin wallet (wallets are at company level)
        wallet_result = bitnob_service.get_bitcoin_wallet()
        if wallet_result.get('error'):
            return None
        
        wallet_id = wallet_result['data']['id']
        
        # Generate Bitcoin address for this customer
        address_result = bitnob_service.generate_customer_address(email)
        if address_result.get('error'):
            return None
        
        return {
            'customer_id': customer_id,
            'wallet_id': wallet_id,
            'bitcoin_address': address_result['data']['address'],
            'address_id': address_result['data']['id']
        }
        
    except Exception as e:
        logger.error(f"Account creation failed: {e}")
        return None

def format_btc_amount(amount: float) -> str:
    """Format BTC amount for display"""
    return f"{amount:.8f} BTC"

def satoshi_to_btc(satoshis: int) -> float:
    """Convert satoshis to BTC"""
    return satoshis / 100000000

def btc_to_satoshi(btc: float) -> int:
    """Convert BTC to satoshis"""
    return int(btc * 100000000)