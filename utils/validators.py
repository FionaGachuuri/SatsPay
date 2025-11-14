import re
from typing import Optional, Dict, Any, List
from decimal import Decimal, InvalidOperation
import logging

logger = logging.getLogger(__name__)

class ValidationError(Exception):
    """Custom validation error"""
    def __init__(self, message: str, field: str = None):
        self.message = message
        self.field = field
        super().__init__(message)

class BitcoinValidator:
    """Bitcoin-specific validators"""
    
    @staticmethod
    def validate_address(address: str) -> Dict[str, Any]:
        """Validate Bitcoin address format"""
        if not address or not isinstance(address, str):
            return {'valid': False, 'error': 'Address is required'}
        
        address = address.strip()
        
        # Legacy address (P2PKH): starts with 1
        if address.startswith('1'):
            if not re.match(r'^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$', address):
                return {'valid': False, 'error': 'Invalid legacy Bitcoin address format'}
            return {'valid': True, 'type': 'legacy'}
        
        # Script address (P2SH): starts with 3
        elif address.startswith('3'):
            if not re.match(r'^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$', address):
                return {'valid': False, 'error': 'Invalid script Bitcoin address format'}
            return {'valid': True, 'type': 'script'}
        
        # Bech32 address: starts with bc1
        elif address.startswith('bc1'):
            if not re.match(r'^bc1[a-z0-9]{39,59}$', address):
                return {'valid': False, 'error': 'Invalid bech32 Bitcoin address format'}
            return {'valid': True, 'type': 'bech32'}
        
        else:
            return {'valid': False, 'error': 'Unsupported Bitcoin address format'}
    
    @staticmethod
    def validate_amount(amount: str) -> Dict[str, Any]:
        """Validate Bitcoin amount"""
        if not amount:
            return {'valid': False, 'error': 'Amount is required'}
        
        try:
            # Clean the amount string
            amount_str = str(amount).replace('BTC', '').replace('btc', '').strip()
            decimal_amount = Decimal(amount_str)
            
            # Check if amount is positive
            if decimal_amount <= 0:
                return {'valid': False, 'error': 'Amount must be greater than zero'}
            
            # Check minimum amount (1 satoshi)
            min_amount = Decimal('0.00000001')
            if decimal_amount < min_amount:
                return {'valid': False, 'error': 'Amount too small (minimum: 0.00000001 BTC)'}
            
            # Check maximum amount (reasonable limit)
            max_amount = Decimal('100')  # 100 BTC per transaction
            if decimal_amount > max_amount:
                return {'valid': False, 'error': 'Amount too large (maximum: 100 BTC per transaction)'}
            
            # Check decimal places (max 8 for Bitcoin)
            if decimal_amount.as_tuple().exponent < -8:
                return {'valid': False, 'error': 'Too many decimal places (maximum: 8)'}
            
            return {
                'valid': True,
                'amount': float(decimal_amount),
                'decimal_amount': decimal_amount
            }
            
        except (InvalidOperation, ValueError, TypeError):
            return {'valid': False, 'error': 'Invalid amount format'}

class UserValidator:
    """User data validators"""
    
    @staticmethod
    def validate_phone_number(phone: str) -> Dict[str, Any]:
        """Validate phone number"""
        if not phone:
            return {'valid': False, 'error': 'Phone number is required'}
        
        # Remove all non-digit characters for validation
        digits_only = re.sub(r'\D', '', phone)
        
        # Check minimum length
        if len(digits_only) < 10:
            return {'valid': False, 'error': 'Phone number too short'}
        
        # Check maximum length
        if len(digits_only) > 15:
            return {'valid': False, 'error': 'Phone number too long'}
        
        # Validate common formats
        valid_patterns = [
            r'^\+?254[17]\d{8}$',  # Kenya
            r'^\+?1[2-9]\d{9}$',   # US/Canada
            r'^\+?44[17]\d{8,9}$', # UK
            r'^\+?\d{10,15}$'      # Generic international
        ]
        
        normalized_phone = phone.strip()
        if not normalized_phone.startswith('+'):
            if digits_only.startswith('254'):
                normalized_phone = f"+{digits_only}"
            elif digits_only.startswith('0') and len(digits_only) == 10:
                normalized_phone = f"+254{digits_only[1:]}"
            else:
                normalized_phone = f"+{digits_only}"
        
        for pattern in valid_patterns:
            if re.match(pattern, normalized_phone):
                return {'valid': True, 'phone': normalized_phone}
        
        return {'valid': False, 'error': 'Invalid phone number format'}
    
    @staticmethod
    def validate_email(email: str) -> Dict[str, Any]:
        """Validate email address"""
        if not email:
            return {'valid': False, 'error': 'Email is required'}
        
        email = email.strip().lower()
        
        # Basic email pattern
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        
        if not re.match(pattern, email):
            return {'valid': False, 'error': 'Invalid email format'}
        
        # Check length limits
        if len(email) > 254:
            return {'valid': False, 'error': 'Email too long'}
        
        # Check for common invalid patterns
        if '..' in email or email.startswith('.') or email.endswith('.'):
            return {'valid': False, 'error': 'Invalid email format'}
        
        return {'valid': True, 'email': email}
    
    @staticmethod
    def validate_full_name(name: str) -> Dict[str, Any]:
        """Validate full name"""
        if not name:
            return {'valid': False, 'error': 'Full name is required'}
        
        name = name.strip()
        
        # Check minimum length
        if len(name) < 2:
            return {'valid': False, 'error': 'Name too short'}
        
        # Check maximum length
        if len(name) > 100:
            return {'valid': False, 'error': 'Name too long'}
        
        # Allow letters, spaces, hyphens, apostrophes
        if not re.match(r"^[a-zA-Z\s\-']+$", name):
            return {'valid': False, 'error': 'Name contains invalid characters'}
        
        # Check for at least one letter
        if not re.search(r'[a-zA-Z]', name):
            return {'valid': False, 'error': 'Name must contain at least one letter'}
        
        # Check for reasonable format (at least two parts)
        name_parts = name.split()
        if len(name_parts) < 2:
            return {'valid': False, 'error': 'Please provide first and last name'}
        
        return {'valid': True, 'name': name}

class OTPValidator:
    """OTP validators"""
    
    @staticmethod
    def validate_otp_code(code: str) -> Dict[str, Any]:
        """Validate OTP code format"""
        if not code:
            return {'valid': False, 'error': 'OTP code is required'}
        
        code = code.strip()
        
        # Check if it's exactly 6 digits
        if not re.match(r'^\d{6}$', code):
            return {'valid': False, 'error': 'OTP must be exactly 6 digits'}
        
        return {'valid': True, 'code': code}

class TransactionValidator:
    """Transaction validators"""
    
    @staticmethod
    def validate_send_transaction(data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate send transaction data"""
        errors = []
        validated_data = {}
        
        # Validate amount
        if 'amount' not in data:
            errors.append('Amount is required')
        else:
            amount_validation = BitcoinValidator.validate_amount(data['amount'])
            if not amount_validation['valid']:
                errors.append(f"Amount: {amount_validation['error']}")
            else:
                validated_data['amount'] = amount_validation['amount']
        
        # Validate recipient address
        if 'address' not in data:
            errors.append('Recipient address is required')
        else:
            address_validation = BitcoinValidator.validate_address(data['address'])
            if not address_validation['valid']:
                errors.append(f"Address: {address_validation['error']}")
            else:
                validated_data['address'] = data['address']
                validated_data['address_type'] = address_validation['type']
        
        # Validate description (optional)
        if 'description' in data and data['description']:
            description = str(data['description']).strip()
            if len(description) > 255:
                errors.append('Description too long (maximum: 255 characters)')
            else:
                validated_data['description'] = description
        
        if errors:
            return {'valid': False, 'errors': errors}
        
        return {'valid': True, 'data': validated_data}
    
    @staticmethod
    def validate_balance_check(user_balance: float, transaction_amount: float, fee: float = 0) -> Dict[str, Any]:
        """Validate user has sufficient balance"""
        total_required = transaction_amount + fee
        
        if user_balance < total_required:
            return {
                'valid': False,
                'error': f'Insufficient balance. Required: {total_required:.8f} BTC, Available: {user_balance:.8f} BTC'
            }
        
        return {'valid': True}

class MessageValidator:
    """Message content validators"""
    
    @staticmethod
    def validate_message_content(message: str) -> Dict[str, Any]:
        """Validate incoming message content"""
        if not message:
            return {'valid': False, 'error': 'Message is empty'}
        
        message = message.strip()
        
        # Check length limits
        if len(message) > 1000:
            return {'valid': False, 'error': 'Message too long'}
        
        # Check for malicious content (basic)
        dangerous_patterns = [
            r'<script.*?</script>',
            r'javascript:',
            r'vbscript:',
            r'onload=',
            r'onerror='
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                return {'valid': False, 'error': 'Message contains invalid content'}
        
        return {'valid': True, 'message': message}

def validate_registration_data(phone: str, full_name: str, email: str) -> Dict[str, Any]:
    """Validate complete registration data"""
    errors = {}
    validated_data = {}
    
    # Validate phone
    phone_result = UserValidator.validate_phone_number(phone)
    if not phone_result['valid']:
        errors['phone'] = phone_result['error']
    else:
        validated_data['phone'] = phone_result['phone']
    
    # Validate name
    name_result = UserValidator.validate_full_name(full_name)
    if not name_result['valid']:
        errors['name'] = name_result['error']
    else:
        validated_data['name'] = name_result['name']
    
    # Validate email
    email_result = UserValidator.validate_email(email)
    if not email_result['valid']:
        errors['email'] = email_result['error']
    else:
        validated_data['email'] = email_result['email']
    
    if errors:
        return {'valid': False, 'errors': errors}
    
    return {'valid': True, 'data': validated_data}

def validate_send_command(message: str) -> Dict[str, Any]:
    """Validate and parse send command"""
    from utils.helpers import parse_send_command
    
    # First validate message content
    message_validation = MessageValidator.validate_message_content(message)
    if not message_validation['valid']:
        return message_validation
    
    # Parse the command
    parsed = parse_send_command(message)
    if not parsed:
        return {
            'valid': False,
            'error': 'Invalid send command format. Use: "Send 0.001 BTC to [address]"'
        }
    
    # Validate the parsed data
    validation_result = TransactionValidator.validate_send_transaction(parsed)
    
    if validation_result['valid']:
        return {
            'valid': True,
            'data': validation_result['data']
        }
    else:
        return {
            'valid': False,
            'errors': validation_result['errors']
        }

# Utility function for comprehensive validation
def validate_user_input(input_type: str, data: Any) -> Dict[str, Any]:
    """Generic validation dispatcher"""
    validators = {
        'phone': UserValidator.validate_phone_number,
        'email': UserValidator.validate_email,
        'name': UserValidator.validate_full_name,
        'bitcoin_address': BitcoinValidator.validate_address,
        'bitcoin_amount': BitcoinValidator.validate_amount,
        'otp': OTPValidator.validate_otp_code,
        'message': MessageValidator.validate_message_content
    }
    
    validator = validators.get(input_type)
    if not validator:
        return {'valid': False, 'error': f'Unknown validation type: {input_type}'}
    
    return validator(data)