import random
import string
from datetime import datetime, timedelta
from typing import Optional
import logging
from models.user import OTP, User

logger = logging.getLogger(__name__)

class OTPService:
    def __init__(self, expiry_minutes: int = 5, max_attempts: int = 3):
        self.expiry_minutes = expiry_minutes
        self.max_attempts = max_attempts
    
    def generate_otp(self, length: int = 6) -> str:
        """Generate random OTP code"""
        return ''.join(random.choices(string.digits, k=length))
    
    def create_otp(self, user: User, purpose: str, transaction_id: Optional[str] = None) -> OTP:
        """Create new OTP for user"""
        # Invalidate any existing OTPs for the same purpose
        existing_otps = OTP.query.filter_by(
            user_id=user.id,
            purpose=purpose,
            is_used=False
        ).all()
        
        for otp in existing_otps:
            otp.is_used = True
            otp.save()
        
        # Generate new OTP
        code = self.generate_otp()
        expires_at = datetime.utcnow() + timedelta(minutes=self.expiry_minutes)
        
        otp = OTP(
            user_id=user.id,
            code=code,
            purpose=purpose,
            expires_at=expires_at,
            max_attempts=self.max_attempts,
            transaction_id=transaction_id
        )
        
        logger.info(f"Created OTP for user {user.phone_number}, purpose: {purpose}")
        return otp.save()
    
    def verify_otp(self, user: User, code: str, purpose: str) -> tuple[bool, Optional[str]]:
        """Verify OTP code"""
        # Get the latest valid OTP for this purpose
        otp = OTP.query.filter_by(
            user_id=user.id,
            purpose=purpose,
            is_used=False
        ).order_by(OTP.created_at.desc()).first()
        
        if not otp:
            logger.warning(f"No valid OTP found for user {user.phone_number}, purpose: {purpose}")
            return False, "No valid OTP found"
        
        # Check if OTP is expired
        if otp.is_expired:
            logger.warning(f"OTP expired for user {user.phone_number}")
            return False, "OTP has expired"
        
        # Check if max attempts exceeded
        if otp.attempts >= otp.max_attempts:
            logger.warning(f"Max OTP attempts exceeded for user {user.phone_number}")
            return False, "Maximum attempts exceeded"
        
        # Verify the code
        if otp.verify(code):
            logger.info(f"OTP verified successfully for user {user.phone_number}")
            user.reset_failed_otp()  # Reset failed attempts on successful verification
            return True, None
        else:
            logger.warning(f"Invalid OTP code for user {user.phone_number}")
            user.increment_failed_otp()  # Increment failed attempts
            
            remaining_attempts = otp.max_attempts - otp.attempts
            if remaining_attempts > 0:
                return False, f"Invalid OTP. {remaining_attempts} attempts remaining"
            else:
                return False, "Invalid OTP. No attempts remaining"
    
    def get_active_otp(self, user: User, purpose: str) -> Optional[OTP]:
        """Get active OTP for user and purpose"""
        return OTP.query.filter_by(
            user_id=user.id,
            purpose=purpose,
            is_used=False
        ).filter(OTP.expires_at > datetime.utcnow()).first()
    
    def invalidate_user_otps(self, user: User, purpose: str = None):
        """Invalidate all OTPs for user"""
        query = OTP.query.filter_by(user_id=user.id, is_used=False)
        
        if purpose:
            query = query.filter_by(purpose=purpose)
        
        otps = query.all()
        for otp in otps:
            otp.is_used = True
            otp.save()
        
        logger.info(f"Invalidated {len(otps)} OTPs for user {user.phone_number}")
    
    def cleanup_expired_otps(self):
        """Clean up expired OTPs (run periodically)"""
        expired_otps = OTP.query.filter(
            OTP.expires_at < datetime.utcnow(),
            OTP.is_used == False
        ).all()
        
        for otp in expired_otps:
            otp.is_used = True
            otp.save()
        
        logger.info(f"Cleaned up {len(expired_otps)} expired OTPs")

# OTP purposes constants
class OTPPurpose:
    REGISTRATION = "registration"
    TRANSACTION = "transaction"
    LOGIN = "login"
    RESET_PIN = "reset_pin"
    ACCOUNT_RECOVERY = "account_recovery"

# Factory function to create OTP service
def create_otp_service(expiry_minutes: int = 5, max_attempts: int = 3) -> OTPService:
    """Create OTP service with configuration"""
    return OTPService(expiry_minutes=expiry_minutes, max_attempts=max_attempts)