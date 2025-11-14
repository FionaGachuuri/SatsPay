import re
import random
import string
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import hashlib
import logging

logger = logging.getLogger(__name__)

def normalize_phone_number(phone: str) -> str:
    """Normalize phone number to international format"""
    # Remove all non-digit characters
    digits_only = re.sub(r'\D', '', phone)
    
    # Handle Kenyan numbers
    if digits_only.startswith('0') and len(digits_only) == 10:
        # Convert 0xxx to +254xxx
        return f"+254{digits_only[1:]}"
    elif digits_only.startswith('254') and len(digits_only) == 12:
        # Add + to 254xxx
        return f"+{digits_only}"
    elif digits_only.startswith('1') and len(digits_only) == 11:
        # US/Canada number
        return f"+{digits_only}"
    elif len(digits_only) >= 10:
        # Assume it needs + prefix
        return f"+{digits_only}"
    
    return phone  # Return as is if we can't normalize

def generate_reference_number(prefix: str = "TXN") -> str:
    """Generate unique transaction reference number"""
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"{prefix}-{timestamp}-{random_suffix}"

def hash_string(text: str) -> str:
    """Generate SHA256 hash of string"""
    return hashlib.sha256(text.encode()).hexdigest()

def mask_sensitive_data(data: str, show_last: int = 4) -> str:
    """Mask sensitive data showing only last N characters"""
    if len(data) <= show_last:
        return "*" * len(data)
    
    masked_length = len(data) - show_last
    return "*" * masked_length + data[-show_last:]

def format_bitcoin_amount(amount: float, decimals: int = 8) -> str:
    """Format Bitcoin amount with proper decimal places"""
    return f"{amount:.{decimals}f}"

def parse_bitcoin_amount(amount_str: str) -> Optional[float]:
    """Parse Bitcoin amount from string"""
    try:
        # Remove BTC suffix if present
        amount_str = amount_str.replace('BTC', '').replace('btc', '').strip()
        amount = float(amount_str)
        
        # Validate amount is positive and not too small
        if amount <= 0:
            return None
        if amount < 0.00000001:  # 1 satoshi minimum
            return None
        if amount > 21000000:  # Max Bitcoin supply
            return None
            
        return amount
    except (ValueError, TypeError):
        return None

def extract_bitcoin_address(text: str) -> Optional[str]:
    """Extract Bitcoin address from text"""
    # Bitcoin address patterns
    # Legacy (P2PKH): starts with 1, 26-35 characters
    # Script (P2SH): starts with 3, 26-35 characters  
    # Bech32 (P2WPKH/P2WSH): starts with bc1, 42 characters
    
    patterns = [
        r'\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b',  # Legacy and Script
        r'\bbc1[a-z0-9]{39,59}\b'  # Bech32
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group()
    
    return None

def parse_send_command(message: str) -> Optional[Dict[str, Any]]:
    """Parse send Bitcoin command from message"""
    # Patterns to match:
    # "Send 0.001 BTC to 1ABC..."
    # "Send 0.001 to 1ABC..."
    # "Transfer 0.001 BTC to 1ABC..."
    
    # Clean message
    message = message.strip().lower()
    
    # Extract amount
    amount_pattern = r'(?:send|transfer)\s+([0-9]*\.?[0-9]+)\s*(?:btc)?\s+to'
    amount_match = re.search(amount_pattern, message)
    
    if not amount_match:
        return None
    
    amount_str = amount_match.group(1)
    amount = parse_bitcoin_amount(amount_str)
    
    if amount is None:
        return None
    
    # Extract Bitcoin address
    address = extract_bitcoin_address(message)
    
    if not address:
        return None
    
    return {
        'amount': amount,
        'address': address,
        'raw_message': message
    }

def is_valid_email(email: str) -> bool:
    """Validate email address"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def is_valid_name(name: str) -> bool:
    """Validate full name"""
    if not name or len(name.strip()) < 2:
        return False
    
    # Should contain only letters, spaces, hyphens, apostrophes
    pattern = r"^[a-zA-Z\s\-']+$"
    return bool(re.match(pattern, name.strip()))

def sanitize_input(text: str, max_length: int = 1000) -> str:
    """Sanitize user input"""
    if not text:
        return ""
    
    # Remove dangerous characters
    sanitized = re.sub(r'[<>"\'\[\]{}\\]', '', text)
    
    # Limit length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    
    return sanitized.strip()

def format_currency(amount: float, currency: str = "BTC", decimals: int = 8) -> str:
    """Format currency amount"""
    if currency.upper() == "BTC":
        return f"{amount:.{decimals}f} BTC"
    else:
        return f"{amount:.2f} {currency}"

def time_ago(dt: datetime) -> str:
    """Get human-readable time difference"""
    now = datetime.utcnow()
    diff = now - dt
    
    if diff.days > 0:
        return f"{diff.days} day{'s' if diff.days != 1 else ''} ago"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    else:
        return "Just now"

def truncate_address(address: str, start_chars: int = 6, end_chars: int = 4) -> str:
    """Truncate Bitcoin address for display"""
    if len(address) <= start_chars + end_chars + 3:
        return address
    
    return f"{address[:start_chars]}...{address[-end_chars:]}"

def detect_message_intent(message: str) -> str:
    """Detect user intent from message"""
    message = message.strip().lower()
    
    # Greeting patterns
    greetings = ['hi', 'hello', 'hey', 'start', 'begin']
    if any(greeting in message for greeting in greetings):
        return 'greeting'
    
    # Send patterns
    send_patterns = ['send', 'transfer', 'pay']
    if any(pattern in message for pattern in send_patterns):
        return 'send'
    
    # Balance patterns
    balance_patterns = ['balance', 'bal', 'money', 'funds']
    if any(pattern in message for pattern in balance_patterns):
        return 'balance'
    
    # History patterns
    history_patterns = ['history', 'transactions', 'activity']
    if any(pattern in message for pattern in history_patterns):
        return 'history'
    
    # Address patterns
    address_patterns = ['address', 'receive', 'deposit']
    if any(pattern in message for pattern in address_patterns):
        return 'address'
    
    # Help patterns
    help_patterns = ['help', 'support', 'assist']
    if any(pattern in message for pattern in help_patterns):
        return 'help'
    
    # Yes/No patterns
    if message in ['yes', 'y', 'ok', 'okay', 'confirm']:
        return 'confirm'
    
    if message in ['no', 'n', 'cancel', 'stop']:
        return 'cancel'
    
    # Check if it's an OTP (6 digits)
    if re.match(r'^\d{6}$', message):
        return 'otp'
    
    # Default to unknown
    return 'unknown'

def create_session_data(state: str, **kwargs) -> str:
    """Create session data JSON string"""
    import json
    data = {
        'state': state,
        'timestamp': datetime.utcnow().isoformat(),
        **kwargs
    }
    return json.dumps(data)

def parse_session_data(session_data: str) -> Dict[str, Any]:
    """Parse session data from JSON string"""
    import json
    try:
        if not session_data:
            return {}
        return json.loads(session_data)
    except (json.JSONDecodeError, TypeError):
        return {}

def is_rate_limited(last_activity: datetime, limit_seconds: int = 60) -> bool:
    """Check if user is rate limited"""
    if not last_activity:
        return False
    
    time_diff = datetime.utcnow() - last_activity
    return time_diff.total_seconds() < limit_seconds

def generate_secure_token(length: int = 32) -> str:
    """Generate secure random token"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

class RateLimiter:
    """Simple in-memory rate limiter"""
    
    def __init__(self):
        self.attempts = {}
    
    def is_allowed(self, key: str, max_attempts: int = 5, window_minutes: int = 5) -> bool:
        """Check if action is allowed within rate limit"""
        now = datetime.utcnow()
        window_start = now - timedelta(minutes=window_minutes)
        
        # Clean old entries
        if key in self.attempts:
            self.attempts[key] = [
                timestamp for timestamp in self.attempts[key]
                if timestamp > window_start
            ]
        
        # Check current attempts
        current_attempts = len(self.attempts.get(key, []))
        
        if current_attempts >= max_attempts:
            return False
        
        # Record this attempt
        if key not in self.attempts:
            self.attempts[key] = []
        
        self.attempts[key].append(now)
        return True

# Global rate limiter instance
rate_limiter = RateLimiter()

def log_user_action(phone_number: str, action: str, details: str = None):
    """Log user action for monitoring"""
    masked_phone = mask_sensitive_data(phone_number, 4)
    log_message = f"User {masked_phone} performed action: {action}"
    
    if details:
        log_message += f" - {details}"
    
    logger.info(log_message)