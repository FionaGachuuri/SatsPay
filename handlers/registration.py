from typing import Dict, Any, Optional
import logging
from models.user import User, UserStatus, get_user_by_phone, create_user
from services.bitnob_service import BitnobService, create_bitnob_account
from services.otp_service import OTPService, OTPPurpose
from services.twilio_service import TwilioService, MessageFormatter
from utils.validators import validate_registration_data, UserValidator
from utils.helpers import log_user_action, normalize_phone_number

logger = logging.getLogger(__name__)

class RegistrationHandler:
    """Handle user registration process"""
    
    def __init__(self, bitnob_service: BitnobService, twilio_service: TwilioService, otp_service: OTPService):
        self.bitnob_service = bitnob_service
        self.twilio_service = twilio_service
        self.otp_service = otp_service
    
    def start_registration(self, phone_number: str) -> Dict[str, Any]:
        """Start user registration process"""
        try:
            phone_number = normalize_phone_number(phone_number)
            
            # Check if user already exists
            existing_user = get_user_by_phone(phone_number)
            
            if existing_user:
                if existing_user.is_kyc_completed:
                    return {
                        'success': False,
                        'message': "You already have an active account!",
                        'next_step': 'account_exists'
                    }
                else:
                    # Resume incomplete registration
                    return self._resume_registration(existing_user)
            
            # Create new user
            user = create_user(phone_number)
            log_user_action(phone_number, "registration_initiated")
            
            return {
                'success': True,
                'message': "Registration started. Please provide your full name:",
                'next_step': 'collect_name',
                'user_id': user.id
            }
            
        except Exception as e:
            logger.error(f"Registration start failed for {phone_number}: {e}")
            return {
                'success': False,
                'message': "Failed to start registration. Please try again.",
                'error': str(e)
            }
    
    def _resume_registration(self, user: User) -> Dict[str, Any]:
        """Resume incomplete registration"""
        try:
            if not user.full_name:
                user.update_session('awaiting_name')
                return {
                    'success': True,
                    'message': "Let's complete your registration. Please provide your full name:",
                    'next_step': 'collect_name',
                    'user_id': user.id
                }
            
            elif not user.email:
                user.update_session('awaiting_email')
                return {
                    'success': True,
                    'message': "Please provide your email address:",
                    'next_step': 'collect_email',
                    'user_id': user.id
                }
            
            elif not user.bitnob_customer_id:
                # KYC data collected but Bitnob account not created
                return self._create_bitnob_account(user)
            
            else:
                # Something went wrong - user should be complete
                logger.warning(f"User {user.phone_number} in inconsistent state during registration resume")
                return {
                    'success': False,
                    'message': "Account setup incomplete. Please contact support.",
                    'next_step': 'contact_support'
                }
                
        except Exception as e:
            logger.error(f"Resume registration failed for {user.phone_number}: {e}")
            return {
                'success': False,
                'message': "Failed to resume registration. Please try again.",
                'error': str(e)
            }
    
    def collect_name(self, user_id: str, full_name: str) -> Dict[str, Any]:
        """Collect and validate user's full name"""
        try:
            user = User.query.get(user_id)
            if not user:
                return {
                    'success': False,
                    'message': "User not found. Please start registration again.",
                    'next_step': 'restart'
                }
            
            # Validate name
            name_validation = UserValidator.validate_full_name(full_name)
            if not name_validation['valid']:
                return {
                    'success': False,
                    'message': f"❌ {name_validation['error']}\n\nPlease provide your full name (first and last name):",
                    'next_step': 'collect_name',
                    'validation_error': True
                }
            
            # Save name and proceed to email collection
            user.full_name = name_validation['name']
            user.update_session('awaiting_email')
            user.save()
            
            log_user_action(user.phone_number, "name_collected")
            
            return {
                'success': True,
                'message': "Thank you! Now please provide your email address:",
                'next_step': 'collect_email',
                'user_id': user.id
            }
            
        except Exception as e:
            logger.error(f"Name collection failed for user {user_id}: {e}")
            return {
                'success': False,
                'message': "Failed to save your name. Please try again.",
                'error': str(e)
            }
    
    def collect_email(self, user_id: str, email: str) -> Dict[str, Any]:
        """Collect and validate user's email"""
        try:
            user = User.query.get(user_id)
            if not user:
                return {
                    'success': False,
                    'message': "User not found. Please start registration again.",
                    'next_step': 'restart'
                }
            
            # Validate email
            email_validation = UserValidator.validate_email(email)
            if not email_validation['valid']:
                return {
                    'success': False,
                    'message': f"❌ {email_validation['error']}\n\nPlease provide a valid email address:",
                    'next_step': 'collect_email',
                    'validation_error': True
                }
            
            # Save email
            user.email = email_validation['email']
            user.save()
            
            log_user_action(user.phone_number, "email_collected")
            
            # Proceed to create Bitnob account
            return self._create_bitnob_account(user)
            
        except Exception as e:
            logger.error(f"Email collection failed for user {user_id}: {e}")
            return {
                'success': False,
                'message': "Failed to save your email. Please try again.",
                'error': str(e)
            }
    
    def _create_bitnob_account(self, user: User) -> Dict[str, Any]:
        """Create Bitnob customer account and wallet"""
        try:
            # Validate we have all required data
            if not user.full_name or not user.email:
                return {
                    'success': False,
                    'message': "Missing registration data. Please start over.",
                    'next_step': 'restart'
                }
            
            # Create Bitnob account
            account_data = create_bitnob_account(
                self.bitnob_service,
                user.full_name,
                user.email,
                user.phone_number
            )
            
            if not account_data:
                # Bitnob account creation failed
                log_user_action(user.phone_number, "bitnob_account_creation_failed")
                
                return {
                    'success': False,
                    'message': MessageFormatter.error_message(
                        "Failed to create your Bitcoin wallet. Please try again later or contact support."
                    ),
                    'next_step': 'retry_bitnob'
                }
            
            # Update user with Bitnob data
            user.bitnob_customer_id = account_data['customer_id']
            user.bitnob_wallet_id = account_data['wallet_id']
            user.bitcoin_address = account_data['bitcoin_address']
            user.is_kyc_completed = True
            user.status = UserStatus.ACTIVE
            user.clear_session()
            user.save()
            
            log_user_action(user.phone_number, "registration_completed")
            
            # Send welcome message
            welcome_message = MessageFormatter.account_created_message(
                user.bitcoin_address,
                "0.00000000"
            )
            
            return {
                'success': True,
                'message': welcome_message,
                'next_step': 'registration_complete',
                'user_data': {
                    'customer_id': user.bitnob_customer_id,
                    'wallet_id': user.bitnob_wallet_id,
                    'bitcoin_address': user.bitcoin_address
                }
            }
            
        except Exception as e:
            logger.error(f"Bitnob account creation failed for {user.phone_number}: {e}")
            return {
                'success': False,
                'message': MessageFormatter.error_message(
                    "Failed to create your Bitcoin wallet. Please try again later."
                ),
                'error': str(e),
                'next_step': 'retry_bitnob'
            }
    
    def retry_bitnob_creation(self, user_id: str) -> Dict[str, Any]:
        """Retry Bitnob account creation"""
        try:
            user = User.query.get(user_id)
            if not user:
                return {
                    'success': False,
                    'message': "User not found. Please start registration again.",
                    'next_step': 'restart'
                }
            
            if user.bitnob_customer_id:
                return {
                    'success': True,
                    'message': "Your account is already set up!",
                    'next_step': 'registration_complete'
                }
            
            return self._create_bitnob_account(user)
            
        except Exception as e:
            logger.error(f"Bitnob retry failed for user {user_id}: {e}")
            return {
                'success': False,
                'message': "Retry failed. Please contact support.",
                'error': str(e)
            }
    
    def validate_registration_step(self, phone_number: str, step: str, data: str) -> Dict[str, Any]:
        """Validate registration data for a specific step"""
        try:
            if step == 'name':
                validation = UserValidator.validate_full_name(data)
                return {
                    'valid': validation['valid'],
                    'message': validation.get('error', 'Valid name'),
                    'data': validation.get('name')
                }
            
            elif step == 'email':
                validation = UserValidator.validate_email(data)
                return {
                    'valid': validation['valid'],
                    'message': validation.get('error', 'Valid email'),
                    'data': validation.get('email')
                }
            
            elif step == 'phone':
                validation = UserValidator.validate_phone_number(data)
                return {
                    'valid': validation['valid'],
                    'message': validation.get('error', 'Valid phone number'),
                    'data': validation.get('phone')
                }
            
            else:
                return {
                    'valid': False,
                    'message': f'Unknown validation step: {step}'
                }
                
        except Exception as e:
            logger.error(f"Validation failed for step {step}: {e}")
            return {
                'valid': False,
                'message': 'Validation error occurred'
            }
    
    def get_registration_status(self, phone_number: str) -> Dict[str, Any]:
        """Get current registration status for user"""
        try:
            phone_number = normalize_phone_number(phone_number)
            user = get_user_by_phone(phone_number)
            
            if not user:
                return {
                    'status': 'not_started',
                    'message': 'Registration not started',
                    'next_step': 'start_registration'
                }
            
            if user.is_kyc_completed and user.bitnob_customer_id:
                return {
                    'status': 'completed',
                    'message': 'Registration completed',
                    'user_data': {
                        'customer_id': user.bitnob_customer_id,
                        'wallet_id': user.bitnob_wallet_id,
                        'bitcoin_address': user.bitcoin_address
                    }
                }
            
            # Determine current step
            if not user.full_name:
                return {
                    'status': 'collecting_name',
                    'message': 'Please provide your full name',
                    'next_step': 'collect_name'
                }
            
            elif not user.email:
                return {
                    'status': 'collecting_email',
                    'message': 'Please provide your email address',
                    'next_step': 'collect_email'
                }
            
            elif not user.bitnob_customer_id:
                return {
                    'status': 'creating_account',
                    'message': 'Creating your Bitcoin wallet...',
                    'next_step': 'create_bitnob_account'
                }
            
            else:
                return {
                    'status': 'incomplete',
                    'message': 'Registration incomplete. Please contact support.',
                    'next_step': 'contact_support'
                }
                
        except Exception as e:
            logger.error(f"Get registration status failed for {phone_number}: {e}")
            return {
                'status': 'error',
                'message': 'Failed to check registration status',
                'error': str(e)
            }
    
    def cancel_registration(self, phone_number: str) -> Dict[str, Any]:
        """Cancel ongoing registration"""
        try:
            phone_number = normalize_phone_number(phone_number)
            user = get_user_by_phone(phone_number)
            
            if not user:
                return {
                    'success': True,
                    'message': 'No registration to cancel'
                }
            
            if user.is_kyc_completed:
                return {
                    'success': False,
                    'message': 'Cannot cancel completed registration'
                }
            
            # Clear session and mark for cleanup
            user.clear_session()
            
            # Note: In production, you might want to mark for deletion
            # rather than immediately deleting, or keep for analytics
            
            log_user_action(phone_number, "registration_cancelled")
            
            return {
                'success': True,
                'message': 'Registration cancelled. You can start over anytime by saying "Hi"'
            }
            
        except Exception as e:
            logger.error(f"Cancel registration failed for {phone_number}: {e}")
            return {
                'success': False,
                'message': 'Failed to cancel registration',
                'error': str(e)
            }

# Utility functions for registration flow
def is_registration_complete(user: User) -> bool:
    """Check if user registration is completely finished"""
    return (
        user is not None and
        user.is_kyc_completed and
        user.bitnob_customer_id is not None and
        user.bitnob_wallet_id is not None and
        user.bitcoin_address is not None and
        user.status == UserStatus.ACTIVE
    )

def get_next_registration_step(user: User) -> str:
    """Get the next step in registration process"""
    if not user:
        return 'start_registration'
    
    if not user.full_name:
        return 'collect_name'
    
    if not user.email:
        return 'collect_email'
    
    if not user.bitnob_customer_id:
        return 'create_bitnob_account'
    
    if is_registration_complete(user):
        return 'completed'
    
    return 'unknown'

def format_registration_progress(user: User) -> str:
    """Format registration progress message"""
    if not user:
        return "Registration not started"
    
    steps_completed = 0
    total_steps = 3
    
    if user.full_name:
        steps_completed += 1
    if user.email:
        steps_completed += 1
    if user.bitnob_customer_id:
        steps_completed += 1
    
    progress_bar = "█" * steps_completed + "░" * (total_steps - steps_completed)
    percentage = int((steps_completed / total_steps) * 100)
    
    return f"Registration Progress: {progress_bar} {percentage}%"

# Factory function
def create_registration_handler(bitnob_service: BitnobService, twilio_service: TwilioService, otp_service: OTPService) -> RegistrationHandler:
    """Create registration handler instance"""
    return RegistrationHandler(bitnob_service, twilio_service, otp_service)