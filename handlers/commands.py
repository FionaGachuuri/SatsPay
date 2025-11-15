from typing import Dict, Any, Optional, Tuple
import logging
from models.user import User, Transaction, TransactionType, TransactionStatus, get_user_by_phone
from services.bitnob_service import BitnobService
from services.twilio_service import MessageFormatter
from services.otp_service import OTPService, OTPPurpose
from utils.helpers import (
    detect_message_intent, parse_send_command, format_bitcoin_amount,
    generate_reference_number, log_user_action, normalize_phone_number,
    normalize_text, strip_sandbox_prefix
)
from utils.validators import (
    validate_send_command, TransactionValidator, BitcoinValidator
)

logger = logging.getLogger(__name__)

class CommandHandler:
    """Handle user commands and interactions"""
    
    def __init__(self, bitnob_service: BitnobService, twilio_service, otp_service: OTPService):
        self.bitnob_service = bitnob_service
        self.twilio_service = twilio_service
        self.otp_service = otp_service
    
    def handle_message(self, phone_number: str, message: str) -> str:
        """Main message handler - routes to appropriate command"""
        try:
            # Normalize phone number
            phone_number = normalize_phone_number(phone_number)
            
            # Clean message: strip sandbox prefixes and normalize
            cleaned_message = strip_sandbox_prefix(message)
            
            # Log user action with cleaned message
            log_user_action(phone_number, "message_received", cleaned_message[:50])
            
            # Get or create user
            user = get_user_by_phone(phone_number)
            
            # Detect intent from cleaned message
            intent = detect_message_intent(cleaned_message)
            
            # Handle based on current session state or intent
            if user and user.current_session_state:
                return self._handle_session_state(user, cleaned_message, intent)
            else:
                return self._handle_intent(user, phone_number, cleaned_message, intent)
                
        except Exception as e:
            logger.error(f"Error handling message from {phone_number}: {e}")
            return MessageFormatter.error_message("Sorry, something went wrong. Please try again.")
    
    def _handle_intent(self, user: Optional[User], phone_number: str, message: str, intent: str) -> str:
        """Handle message based on detected intent"""
        
        # Handle greeting - always show appropriate welcome message
        if intent == 'greeting':
            return self._handle_greeting(user, phone_number)
        
        # Handle confirmation (YES/yes/Yes etc.)
        if intent == 'confirm':
            if not user:
                # User wants to start registration
                return self._handle_registration_start(phone_number)
            elif user and not user.is_kyc_completed:
                # User exists but registration not complete - resume registration
                return self._handle_registration_start(phone_number)
            else:
                # User is complete - this might be confirming something else
                return MessageFormatter.error_message("Nothing to confirm right now. Try 'Help' for available commands.")
        
        # Check if user exists and is complete for transactional commands
        if user and user.is_kyc_completed:
            if intent == 'send':
                return self._handle_send_command(user, message)
            elif intent == 'balance':
                return self._handle_balance_command(user)
            elif intent == 'history':
                return self._handle_history_command(user)
            elif intent == 'address':
                return self._handle_address_command(user)
        
        # Handle commands for incomplete users
        elif user and not user.is_kyc_completed:
            if intent in ['send', 'balance', 'history', 'address']:
                return MessageFormatter.error_message(
                    "⚠️ Your account setup is not complete.\n\n"
                    "Please complete your registration first. Reply *YES* to continue setup."
                )
            elif intent == 'help':
                return MessageFormatter.help_message()
            else:
                # Try to resume registration
                return self._handle_registration_start(phone_number)
        
        # Handle help - always available
        elif intent == 'help':
            return MessageFormatter.help_message()
        
        # Handle no user - show welcome
        elif not user:
            return MessageFormatter.welcome_message()
        
        # Handle unknown commands
        else:
            if user and user.is_kyc_completed:
                return MessageFormatter.invalid_command_message()
            else:
                return MessageFormatter.welcome_message()
    
    def _handle_session_state(self, user: User, message: str, intent: str) -> str:
        """Handle message based on current session state"""
        
        state = user.current_session_state
        
        if state == 'awaiting_name':
            return self._handle_name_input(user, message)
        
        elif state == 'awaiting_email':
            return self._handle_email_input(user, message)
        
        elif state == 'awaiting_transaction_confirmation':
            return self._handle_transaction_confirmation(user, message, intent)
        
        elif state == 'awaiting_otp':
            return self._handle_otp_input(user, message, intent)
        
        else:
            # Clear invalid session state and handle normally
            logger.warning(f"User {user.phone_number} had invalid session state: {state}")
            user.clear_session()
            return self._handle_intent(user, user.phone_number, message, intent)
    
    def _handle_greeting(self, user: Optional[User], phone_number: str) -> str:
        """Handle greeting message"""
        if user and user.is_kyc_completed:
            # Get balance for returning user
            balance = self._get_user_balance(user)
            return f"👋 *Hello! Welcome back to SatChat.*\n\n💰 Your balance: {balance} BTC\n\nHow can I help you today?\n\nTry: Balance • Send • History • Address • Help"
        elif user and not user.is_kyc_completed:
            return f"👋 *Welcome back!*\n\nYour account setup is not complete. Reply *YES* to continue registration."
        else:
            return MessageFormatter.welcome_message()
    
    def _handle_registration_start(self, phone_number: str) -> str:
        """Start user registration process"""
        try:
            # Check if user already exists
            existing_user = get_user_by_phone(phone_number)
            if existing_user:
                if existing_user.is_kyc_completed:
                    return "You already have an account! Use 'Balance' to check your Bitcoin balance."
                else:
                    # Resume registration
                    if not existing_user.full_name:
                        existing_user.update_session('awaiting_name')
                        return "Let's complete your account setup. Please provide your full name:"
                    elif not existing_user.email:
                        existing_user.update_session('awaiting_email')
                        return "Please provide your email address:"
            
            # Create new user
            from models.user import create_user
            user = create_user(phone_number)
            user.update_session('awaiting_name')
            
            log_user_action(phone_number, "registration_started")
            
            return "Great! Let's create your Bitcoin wallet. Please provide your full name:"
            
        except Exception as e:
            logger.error(f"Registration start failed for {phone_number}: {e}")
            return MessageFormatter.error_message("Failed to start registration. Please try again.")
    
    def _handle_name_input(self, user: User, message: str) -> str:
        """Handle name input during registration"""
        from utils.validators import UserValidator
        
        # First check if user is trying to cancel
        if normalize_text(message) in ['cancel', 'stop', 'exit', 'quit', 'no']:
            user.clear_session()
            return "Registration cancelled. Reply *YES* anytime to start again."
        
        validation = UserValidator.validate_full_name(message)
        if not validation['valid']:
            return f"❌ {validation['error']}\n\nPlease provide your full name (first and last name):\n\n_Or reply CANCEL to stop._"
        
        user.full_name = validation['name']
        user.update_session('awaiting_email')
        user.save()
        
        log_user_action(user.phone_number, "name_provided", user.full_name)
        
        return f"Great! Hi *{user.full_name}*\n\nNow please provide your email address:"
    
    def _handle_email_input(self, user: User, message: str) -> str:
        """Handle email input during registration"""
        from utils.validators import UserValidator
        
        # First check if user is trying to cancel
        if normalize_text(message) in ['cancel', 'stop', 'exit', 'quit', 'no']:
            user.clear_session()
            return "Registration cancelled. Reply *YES* anytime to start again."
        
        validation = UserValidator.validate_email(message)
        if not validation['valid']:
            return f"❌ {validation['error']}\n\nPlease provide a valid email address:\n\n_Or reply CANCEL to stop._"
        
        user.email = validation['email']
        user.save()
        
        log_user_action(user.phone_number, "email_provided", user.email)
        
        # Complete Bitnob account creation
        return self._complete_bitnob_registration(user)
    
    def _complete_bitnob_registration(self, user: User) -> str:
        """Complete Bitnob account creation"""
        try:
            from services.bitnob_service import create_bitnob_account
            
            # Show progress message
            logger.info(f"Creating Bitnob account for {user.phone_number}")
            
            # Create Bitnob account
            account_data = create_bitnob_account(
                self.bitnob_service,
                user.full_name,
                user.email,
                user.phone_number
            )
            
            if not account_data:
                logger.error(f"Bitnob account creation failed for {user.phone_number}")
                user.clear_session()
                return MessageFormatter.error_message(
                    "⚠️ Failed to create your Bitcoin wallet.\n\n"
                    "This might be temporary. Please try again in a few minutes or reply *YES* to retry.\n\n"
                    "If the problem persists, contact support."
                )
            
            # Update user with Bitnob data
            user.bitnob_customer_id = account_data['customer_id']
            user.bitnob_wallet_id = account_data['wallet_id']
            user.bitcoin_address = account_data['bitcoin_address']
            user.is_kyc_completed = True
            user.status = user.UserStatus.ACTIVE
            user.clear_session()
            user.save()
            
            log_user_action(user.phone_number, "registration_completed", 
                          f"Customer ID: {account_data['customer_id']}")
            
            # Get initial balance
            initial_balance = self._get_user_balance(user) or "0.00000000"
            
            return MessageFormatter.account_created_message(
                user.bitcoin_address,
                initial_balance
            )
            
        except Exception as e:
            logger.error(f"Bitnob registration failed for {user.phone_number}: {e}")
            user.clear_session()
            return MessageFormatter.error_message(
                "Failed to create your Bitcoin wallet. Please try again later."
            )
    
    def _handle_send_command(self, user: User, message: str) -> str:
        """Handle Bitcoin send command"""
        try:
            # Check if user account is ready
            if not user.is_kyc_completed or not user.bitnob_wallet_id:
                return MessageFormatter.error_message(
                    "Your account is not fully set up. Please complete registration first."
                )
            
            # Check if account is locked
            if user.is_account_locked:
                return MessageFormatter.error_message(
                    "Your account is temporarily locked. Please try again later."
                )
            
            # Validate send command
            validation = validate_send_command(message)
            if not validation['valid']:
                if 'errors' in validation:
                    error_msg = "\n".join(validation['errors'])
                else:
                    error_msg = validation['error']
                
                return MessageFormatter.error_message(
                    f"Invalid send command:\n{error_msg}\n\nUse: Send 0.001 BTC to [address]"
                )
            
            send_data = validation['data']
            
            # Check user balance
            current_balance = self._get_user_balance_float(user)
            if current_balance is None:
                return MessageFormatter.error_message(
                    "Unable to check your balance. Please try again."
                )
            
            # Estimate fee (simplified - you may want to call Bitnob API)
            estimated_fee = 0.00001  # 1000 satoshis
            
            balance_check = TransactionValidator.validate_balance_check(
                current_balance, send_data['amount'], estimated_fee
            )
            
            if not balance_check['valid']:
                return MessageFormatter.error_message(balance_check['error'])
            
            # Create pending transaction
            from models.user import create_transaction
            reference = generate_reference_number()
            
            transaction = create_transaction(
                user_id=user.id,
                transaction_type=TransactionType.SEND,
                amount=send_data['amount'],
                recipient_address=send_data['address'],
                reference_number=reference,
                description=send_data.get('description', ''),
                fee=estimated_fee
            )
            
            # Store transaction data in session
            from utils.helpers import create_session_data
            session_data = create_session_data(
                'awaiting_transaction_confirmation',
                transaction_id=transaction.id,
                amount=send_data['amount'],
                address=send_data['address'],
                reference=reference,
                fee=estimated_fee
            )
            
            user.update_session('awaiting_transaction_confirmation', session_data)
            
            # Format confirmation message
            recipient_name = "Unknown"  # You could implement address book lookup
            
            return MessageFormatter.transaction_confirmation(
                format_bitcoin_amount(send_data['amount']),
                recipient_name,
                send_data['address'],
                reference,
                format_bitcoin_amount(estimated_fee)
            )
            
        except Exception as e:
            logger.error(f"Send command failed for {user.phone_number}: {e}")
            return MessageFormatter.error_message(
                "Failed to process send command. Please try again."
            )
    
    def _handle_transaction_confirmation(self, user: User, message: str, intent: str) -> str:
        """Handle transaction confirmation response"""
        try:
            if intent == 'confirm':
                # Generate and send OTP
                otp = self.otp_service.create_otp(user, OTPPurpose.TRANSACTION)
                
                # Send OTP via WhatsApp
                otp_result = self.twilio_service.send_otp(
                    user.phone_number, otp.code, 'transaction'
                )
                
                if not otp_result['success']:
                    logger.error(f"Failed to send OTP to {user.phone_number}")
                    user.clear_session()
                    return MessageFormatter.error_message(
                        "Failed to send verification code. Please try again."
                    )
                
                user.update_session('awaiting_otp', user.session_data)
                
                log_user_action(user.phone_number, "transaction_otp_sent")
                
                return MessageFormatter.otp_prompt()
            
            elif intent == 'cancel':
                # Cancel transaction
                session_data = user.session_data
                if session_data:
                    from utils.helpers import parse_session_data
                    data = parse_session_data(session_data)
                    transaction_id = data.get('transaction_id')
                    
                    if transaction_id:
                        transaction = Transaction.query.get(transaction_id)
                        if transaction:
                            transaction.status = TransactionStatus.CANCELLED
                            transaction.save()
                
                user.clear_session()
                log_user_action(user.phone_number, "transaction_cancelled")
                
                return "❌ Transaction cancelled. Your Bitcoin is safe in your wallet."
            
            else:
                return "Please reply *YES* to confirm the transaction or *NO* to cancel."
                
        except Exception as e:
            logger.error(f"Transaction confirmation failed for {user.phone_number}: {e}")
            user.clear_session()
            return MessageFormatter.error_message("Transaction cancelled due to an error.")
    
    def _handle_otp_input(self, user: User, message: str, intent: str) -> str:
        """Handle OTP input for transaction authorization"""
        try:
            if intent == 'cancel':
                user.clear_session()
                return "❌ Transaction cancelled."
            
            # Validate OTP format
            from utils.validators import OTPValidator
            otp_validation = OTPValidator.validate_otp_code(message)
            
            if not otp_validation['valid']:
                return f"❌ {otp_validation['error']}\n\nPlease enter the 6-digit code sent to your phone:"
            
            # Verify OTP
            verification_result = self.otp_service.verify_otp(
                user, otp_validation['code'], OTPPurpose.TRANSACTION
            )
            
            if not verification_result[0]:  # OTP verification failed
                error_msg = verification_result[1]
                return f"❌ {error_msg}\n\nPlease try again or reply CANCEL to cancel the transaction."
            
            # OTP verified - execute transaction
            return self._execute_transaction(user)
            
        except Exception as e:
            logger.error(f"OTP handling failed for {user.phone_number}: {e}")
            user.clear_session()
            return MessageFormatter.error_message("Transaction cancelled due to an error.")
    
    def _execute_transaction(self, user: User) -> str:
        """Execute the Bitcoin transaction"""
        try:
            from utils.helpers import parse_session_data
            
            # Get transaction data from session
            session_data = parse_session_data(user.session_data)
            transaction_id = session_data.get('transaction_id')
            
            if not transaction_id:
                user.clear_session()
                return MessageFormatter.error_message("Transaction data not found.")
            
            transaction = Transaction.query.get(transaction_id)
            if not transaction:
                user.clear_session()
                return MessageFormatter.error_message("Transaction not found.")
            
            # Update transaction status
            transaction.status = TransactionStatus.PROCESSING
            transaction.save()
            
            # Execute via Bitnob
            send_result = self.bitnob_service.send_bitcoin(
                user.bitnob_wallet_id,
                transaction.recipient_address,
                float(transaction.amount),
                f"SatChat transaction {transaction.reference_number}"
            )
            
            if send_result.get('error'):
                # Transaction failed
                transaction.mark_failed(send_result.get('message', 'Unknown error'))
                user.clear_session()
                
                log_user_action(user.phone_number, "transaction_failed", send_result.get('message'))
                
                return MessageFormatter.transaction_failed(
                    send_result.get('message', 'Transaction failed. Please try again.')
                )
            
            # Transaction successful
            bitnob_tx_id = send_result.get('data', {}).get('id')
            if bitnob_tx_id:
                transaction.bitnob_transaction_id = bitnob_tx_id
            
            transaction.mark_completed()
            user.clear_session()
            
            # Get updated balance
            new_balance = self._get_user_balance(user)
            
            log_user_action(user.phone_number, "transaction_completed", transaction.reference_number)
            
            return MessageFormatter.transaction_success(
                format_bitcoin_amount(float(transaction.amount)),
                "Recipient",
                transaction.reference_number,
                new_balance
            )
            
        except Exception as e:
            logger.error(f"Transaction execution failed for {user.phone_number}: {e}")
            user.clear_session()
            return MessageFormatter.error_message("Transaction failed. Please try again.")
    
    def _handle_balance_command(self, user: User) -> str:
        """Handle balance check command"""
        try:
            if not user.is_kyc_completed or not user.bitnob_wallet_id:
                return MessageFormatter.error_message(
                    "Your account is not fully set up. Please complete registration first."
                )
            
            balance = self._get_user_balance(user)
            if balance is None:
                return MessageFormatter.error_message(
                    "Unable to retrieve balance. Please try again."
                )
            
            log_user_action(user.phone_number, "balance_checked")
            
            return MessageFormatter.balance_message(balance, user.bitcoin_address)
            
        except Exception as e:
            logger.error(f"Balance check failed for {user.phone_number}: {e}")
            return MessageFormatter.error_message("Unable to check balance. Please try again.")
    
    def _handle_history_command(self, user: User) -> str:
        """Handle transaction history command"""
        try:
            if not user.is_kyc_completed:
                return MessageFormatter.error_message(
                    "Your account is not fully set up. Please complete registration first."
                )
            
            from models.user import get_user_transactions
            transactions = get_user_transactions(user.id, limit=5)
            
            if not transactions:
                return "📊 *Transaction History*\n\nNo transactions found.\n\nYour wallet is ready to send and receive Bitcoin!"
            
            history_text = "📊 *Transaction History*\n\n"
            
            for tx in transactions:
                status_emoji = {
                    TransactionStatus.COMPLETED: "✅",
                    TransactionStatus.PENDING: "⏳",
                    TransactionStatus.PROCESSING: "🔄",
                    TransactionStatus.FAILED: "❌",
                    TransactionStatus.CANCELLED: "🚫"
                }.get(tx.status, "❓")
                
                type_text = "Sent" if tx.transaction_type == TransactionType.SEND else "Received"
                amount_text = format_bitcoin_amount(float(tx.amount))
                
                history_text += f"{status_emoji} {type_text} {amount_text} BTC\n"
                history_text += f"   {tx.created_at.strftime('%Y-%m-%d %H:%M')}\n"
                history_text += f"   Ref: {tx.reference_number}\n\n"
            
            log_user_action(user.phone_number, "history_viewed")
            
            return history_text
            
        except Exception as e:
            logger.error(f"History command failed for {user.phone_number}: {e}")
            return MessageFormatter.error_message("Unable to retrieve history. Please try again.")
    
    def _handle_address_command(self, user: User) -> str:
        """Handle address request command"""
        try:
            if not user.is_kyc_completed or not user.bitcoin_address:
                return MessageFormatter.error_message(
                    "Your account is not fully set up. Please complete registration first."
                )
            
            log_user_action(user.phone_number, "address_requested")
            
            return f"""🔗 *Your Bitcoin Address*

`{user.bitcoin_address}`

Share this address to receive Bitcoin payments.

⚠️ Only send Bitcoin (BTC) to this address.
⚠️ Double-check the address before sharing."""
            
        except Exception as e:
            logger.error(f"Address command failed for {user.phone_number}: {e}")
            return MessageFormatter.error_message("Unable to get address. Please try again.")
    
    def _get_user_balance(self, user: User) -> Optional[str]:
        """Get formatted user balance"""
        balance_float = self._get_user_balance_float(user)
        if balance_float is None:
            return None
        return format_bitcoin_amount(balance_float)
    
    def _get_user_balance_float(self, user: User) -> Optional[float]:
        """Get user balance as float"""
        try:
            if not user.bitnob_wallet_id:
                return 0.0
            
            balance_result = self.bitnob_service.get_wallet_balance(user.bitnob_wallet_id)
            
            if balance_result.get('error'):
                logger.error(f"Failed to get balance for {user.phone_number}: {balance_result.get('message')}")
                return None
            
            balance_data = balance_result.get('data', {})
            return float(balance_data.get('available', 0))
            
        except Exception as e:
            logger.error(f"Balance retrieval failed for {user.phone_number}: {e}")
            return None

# Factory function
def create_command_handler(bitnob_service: BitnobService, twilio_service, otp_service: OTPService) -> CommandHandler:
    """Create command handler instance"""
    return CommandHandler(bitnob_service, twilio_service, otp_service)