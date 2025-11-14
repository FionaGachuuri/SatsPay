from typing import Dict, Any, Optional, List
import logging
from datetime import datetime
from models.user import User, Transaction, TransactionType, TransactionStatus, get_user_by_phone
from services.bitnob_service import BitnobService
from services.otp_service import OTPService, OTPPurpose
from services.twilio_service import TwilioService, MessageFormatter
from utils.helpers import (
    generate_reference_number, format_bitcoin_amount, log_user_action,
    normalize_phone_number, parse_session_data, create_session_data
)
from utils.validators import TransactionValidator, BitcoinValidator

logger = logging.getLogger(__name__)

class TransactionHandler:
    """Handle Bitcoin transactions"""
    
    def __init__(self, bitnob_service: BitnobService, twilio_service: TwilioService, otp_service: OTPService):
        self.bitnob_service = bitnob_service
        self.twilio_service = twilio_service
        self.otp_service = otp_service
    
    def initiate_send(self, user: User, recipient_address: str, amount: float, description: str = "") -> Dict[str, Any]:
        """Initiate Bitcoin send transaction"""
        try:
            # Validate user account
            account_check = self._validate_user_account(user)
            if not account_check['valid']:
                return account_check
            
            # Validate transaction data
            transaction_data = {
                'amount': amount,
                'address': recipient_address,
                'description': description
            }
            
            validation = TransactionValidator.validate_send_transaction(transaction_data)
            if not validation['valid']:
                return {
                    'success': False,
                    'message': self._format_validation_errors(validation['errors']),
                    'type': 'validation_error'
                }
            
            validated_data = validation['data']
            
            # Check user balance
            balance_check = self._check_user_balance(user, validated_data['amount'])
            if not balance_check['valid']:
                return {
                    'success': False,
                    'message': balance_check['message'],
                    'type': 'insufficient_balance'
                }
            
            # Estimate transaction fee
            fee_estimate = self._estimate_transaction_fee(validated_data['amount'])
            
            # Final balance check including fee
            total_required = validated_data['amount'] + fee_estimate
            final_balance_check = self._check_user_balance(user, total_required)
            if not final_balance_check['valid']:
                return {
                    'success': False,
                    'message': f"Insufficient balance including network fee. Required: {format_bitcoin_amount(total_required)} BTC",
                    'type': 'insufficient_balance_with_fee'
                }
            
            # Create pending transaction
            reference = generate_reference_number("TXN")
            transaction = Transaction(
                user_id=user.id,
                transaction_type=TransactionType.SEND,
                amount=validated_data['amount'],
                recipient_address=validated_data['address'],
                reference_number=reference,
                description=validated_data.get('description', ''),
                fee=fee_estimate,
                status=TransactionStatus.PENDING
            )
            transaction.save()
            
            # Store transaction in user session
            session_data = create_session_data(
                'awaiting_transaction_confirmation',
                transaction_id=transaction.id,
                amount=validated_data['amount'],
                address=validated_data['address'],
                reference=reference,
                fee=fee_estimate
            )
            
            user.update_session('awaiting_transaction_confirmation', session_data)
            
            log_user_action(user.phone_number, "transaction_initiated", reference)
            
            # Format confirmation message
            recipient_name = self._get_recipient_name(validated_data['address'])
            
            confirmation_message = MessageFormatter.transaction_confirmation(
                format_bitcoin_amount(validated_data['amount']),
                recipient_name,
                validated_data['address'],
                reference,
                format_bitcoin_amount(fee_estimate) if fee_estimate > 0 else None
            )
            
            return {
                'success': True,
                'message': confirmation_message,
                'transaction_id': transaction.id,
                'reference': reference,
                'requires_confirmation': True
            }
            
        except Exception as e:
            logger.error(f"Transaction initiation failed for {user.phone_number}: {e}")
            return {
                'success': False,
                'message': "Failed to initiate transaction. Please try again.",
                'type': 'system_error',
                'error': str(e)
            }
    
    def confirm_transaction(self, user: User, confirmed: bool) -> Dict[str, Any]:
        """Handle transaction confirmation"""
        try:
            if not user.current_session_state == 'awaiting_transaction_confirmation':
                return {
                    'success': False,
                    'message': "No pending transaction to confirm.",
                    'type': 'no_pending_transaction'
                }
            
            session_data = parse_session_data(user.session_data)
            transaction_id = session_data.get('transaction_id')
            
            if not transaction_id:
                user.clear_session()
                return {
                    'success': False,
                    'message': "Transaction data not found. Please try again.",
                    'type': 'missing_transaction_data'
                }
            
            transaction = Transaction.query.get(transaction_id)
            if not transaction:
                user.clear_session()
                return {
                    'success': False,
                    'message': "Transaction not found. Please try again.",
                    'type': 'transaction_not_found'
                }
            
            if not confirmed:
                # User cancelled transaction
                transaction.status = TransactionStatus.CANCELLED
                transaction.save()
                user.clear_session()
                
                log_user_action(user.phone_number, "transaction_cancelled", transaction.reference_number)
                
                return {
                    'success': True,
                    'message': "❌ Transaction cancelled. Your Bitcoin is safe in your wallet.",
                    'type': 'cancelled'
                }
            
            # User confirmed - generate OTP
            otp = self.otp_service.create_otp(user, OTPPurpose.TRANSACTION, transaction_id)
            
            # Send OTP
            otp_result = self.twilio_service.send_otp(
                user.phone_number, otp.code, 'transaction'
            )
            
            if not otp_result['success']:
                logger.error(f"Failed to send OTP to {user.phone_number}: {otp_result}")
                user.clear_session()
                transaction.status = TransactionStatus.FAILED
                transaction.save()
                
                return {
                    'success': False,
                    'message': "Failed to send verification code. Transaction cancelled.",
                    'type': 'otp_send_failed'
                }
            
            # Update session state
            user.update_session('awaiting_otp', user.session_data)
            
            log_user_action(user.phone_number, "transaction_otp_sent", transaction.reference_number)
            
            return {
                'success': True,
                'message': MessageFormatter.otp_prompt(),
                'type': 'otp_sent',
                'requires_otp': True
            }
            
        except Exception as e:
            logger.error(f"Transaction confirmation failed for {user.phone_number}: {e}")
            user.clear_session()
            return {
                'success': False,
                'message': "Transaction confirmation failed. Please try again.",
                'type': 'system_error',
                'error': str(e)
            }
    
    def verify_and_execute(self, user: User, otp_code: str) -> Dict[str, Any]:
        """Verify OTP and execute transaction"""
        try:
            if user.current_session_state != 'awaiting_otp':
                return {
                    'success': False,
                    'message': "No pending OTP verification.",
                    'type': 'no_pending_otp'
                }
            
            # Verify OTP
            verification_result = self.otp_service.verify_otp(
                user, otp_code, OTPPurpose.TRANSACTION
            )
            
            if not verification_result[0]:
                error_message = verification_result[1]
                return {
                    'success': False,
                    'message': f"❌ {error_message}\n\nPlease try again or reply CANCEL to cancel the transaction.",
                    'type': 'otp_verification_failed',
                    'can_retry': True
                }
            
            # OTP verified - execute transaction
            return self._execute_transaction(user)
            
        except Exception as e:
            logger.error(f"OTP verification failed for {user.phone_number}: {e}")
            user.clear_session()
            return {
                'success': False,
                'message': "Verification failed. Transaction cancelled.",
                'type': 'system_error',
                'error': str(e)
            }
    
    def _execute_transaction(self, user: User) -> Dict[str, Any]:
        """Execute the Bitcoin transaction via Bitnob"""
        try:
            session_data = parse_session_data(user.session_data)
            transaction_id = session_data.get('transaction_id')
            
            if not transaction_id:
                user.clear_session()
                return {
                    'success': False,
                    'message': "Transaction data not found.",
                    'type': 'missing_transaction_data'
                }
            
            transaction = Transaction.query.get(transaction_id)
            if not transaction:
                user.clear_session()
                return {
                    'success': False,
                    'message': "Transaction not found.",
                    'type': 'transaction_not_found'
                }
            
            # Update transaction status to processing
            transaction.status = TransactionStatus.PROCESSING
            transaction.save()
            
            # Execute via Bitnob API
            send_result = self.bitnob_service.send_bitcoin(
                user.bitnob_wallet_id,
                transaction.recipient_address,
                float(transaction.amount),
                f"SatChat transaction {transaction.reference_number}"
            )
            
            if send_result.get('error'):
                # Transaction failed
                error_message = send_result.get('message', 'Unknown error')
                transaction.mark_failed(error_message)
                user.clear_session()
                
                log_user_action(user.phone_number, "transaction_failed", 
                              f"{transaction.reference_number}: {error_message}")
                
                return {
                    'success': False,
                    'message': MessageFormatter.transaction_failed(error_message),
                    'type': 'execution_failed',
                    'reference': transaction.reference_number
                }
            
            # Transaction successful
            bitnob_tx_data = send_result.get('data', {})
            bitnob_tx_id = bitnob_tx_data.get('id')
            blockchain_hash = bitnob_tx_data.get('hash')
            
            if bitnob_tx_id:
                transaction.bitnob_transaction_id = bitnob_tx_id
            
            if blockchain_hash:
                transaction.blockchain_hash = blockchain_hash
            
            transaction.mark_completed(blockchain_hash)
            user.clear_session()
            
            # Get updated balance
            new_balance = self._get_user_balance(user)
            
            log_user_action(user.phone_number, "transaction_completed", transaction.reference_number)
            
            success_message = MessageFormatter.transaction_success(
                format_bitcoin_amount(float(transaction.amount)),
                self._get_recipient_name(transaction.recipient_address),
                transaction.reference_number,
                new_balance or "N/A",
                blockchain_hash
            )
            
            return {
                'success': True,
                'message': success_message,
                'type': 'completed',
                'transaction_data': {
                    'reference': transaction.reference_number,
                    'amount': float(transaction.amount),
                    'recipient_address': transaction.recipient_address,
                    'blockchain_hash': blockchain_hash,
                    'new_balance': new_balance
                }
            }
            
        except Exception as e:
            logger.error(f"Transaction execution failed for {user.phone_number}: {e}")
            user.clear_session()
            
            # Try to mark transaction as failed
            try:
                if 'transaction' in locals():
                    transaction.mark_failed(f"Execution error: {str(e)}")
            except:
                pass
            
            return {
                'success': False,
                'message': "Transaction execution failed. Please contact support if funds were deducted.",
                'type': 'execution_error',
                'error': str(e)
            }
    
    def get_transaction_history(self, user: User, limit: int = 10) -> Dict[str, Any]:
        """Get user's transaction history"""
        try:
            if not user.is_kyc_completed:
                return {
                    'success': False,
                    'message': "Account not fully set up.",
                    'type': 'account_not_ready'
                }
            
            from models.user import get_user_transactions
            transactions = get_user_transactions(user.id, limit)
            
            if not transactions:
                return {
                    'success': True,
                    'message': "📊 *Transaction History*\n\nNo transactions found.\n\nYour wallet is ready to send and receive Bitcoin!",
                    'transactions': [],
                    'type': 'empty_history'
                }
            
            # Format transaction history
            history_text = "📊 *Transaction History*\n\n"
            transaction_list = []
            
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
                
                # Add to structured list
                transaction_list.append({
                    'id': tx.id,
                    'type': tx.transaction_type.value,
                    'amount': float(tx.amount),
                    'status': tx.status.value,
                    'reference': tx.reference_number,
                    'created_at': tx.created_at.isoformat(),
                    'recipient_address': tx.recipient_address,
                    'blockchain_hash': tx.blockchain_hash
                })
            
            log_user_action(user.phone_number, "history_viewed")
            
            return {
                'success': True,
                'message': history_text.strip(),
                'transactions': transaction_list,
                'type': 'history_retrieved'
            }
            
        except Exception as e:
            logger.error(f"Get transaction history failed for {user.phone_number}: {e}")
            return {
                'success': False,
                'message': "Unable to retrieve transaction history. Please try again.",
                'type': 'system_error',
                'error': str(e)
            }
    
    def get_transaction_status(self, user: User, reference: str) -> Dict[str, Any]:
        """Get status of a specific transaction"""
        try:
            transaction = Transaction.query.filter_by(
                user_id=user.id,
                reference_number=reference
            ).first()
            
            if not transaction:
                return {
                    'success': False,
                    'message': f"Transaction {reference} not found.",
                    'type': 'transaction_not_found'
                }
            
            # If transaction is processing, check Bitnob status
            if (transaction.status == TransactionStatus.PROCESSING and 
                transaction.bitnob_transaction_id):
                
                self._update_transaction_status(transaction)
            
            status_text = {
                TransactionStatus.PENDING: "⏳ Pending confirmation",
                TransactionStatus.PROCESSING: "🔄 Processing on network",
                TransactionStatus.COMPLETED: "✅ Completed successfully",
                TransactionStatus.FAILED: "❌ Failed",
                TransactionStatus.CANCELLED: "🚫 Cancelled"
            }.get(transaction.status, "❓ Unknown status")
            
            message = f"Transaction {reference}:\n{status_text}"
            
            if transaction.status == TransactionStatus.COMPLETED and transaction.blockchain_hash:
                message += f"\n🔗 Hash: `{transaction.blockchain_hash}`"
            
            return {
                'success': True,
                'message': message,
                'transaction_data': {
                    'reference': transaction.reference_number,
                    'status': transaction.status.value,
                    'amount': float(transaction.amount),
                    'type': transaction.transaction_type.value,
                    'created_at': transaction.created_at.isoformat(),
                    'completed_at': transaction.completed_at.isoformat() if transaction.completed_at else None,
                    'blockchain_hash': transaction.blockchain_hash
                },
                'type': 'status_retrieved'
            }
            
        except Exception as e:
            logger.error(f"Get transaction status failed for {user.phone_number}: {e}")
            return {
                'success': False,
                'message': "Unable to check transaction status. Please try again.",
                'type': 'system_error',
                'error': str(e)
            }
    
    def _validate_user_account(self, user: User) -> Dict[str, Any]:
        """Validate user account is ready for transactions"""
        if not user.is_kyc_completed or not user.bitnob_wallet_id:
            return {
                'valid': False,
                'message': "Your account is not fully set up. Please complete registration first.",
                'type': 'account_not_ready'
            }
        
        if user.is_account_locked:
            return {
                'valid': False,
                'message': "Your account is temporarily locked. Please try again later.",
                'type': 'account_locked'
            }
        
        return {'valid': True}
    
    def _check_user_balance(self, user: User, required_amount: float) -> Dict[str, Any]:
        """Check if user has sufficient balance"""
        try:
            current_balance = self._get_user_balance_float(user)
            
            if current_balance is None:
                return {
                    'valid': False,
                    'message': "Unable to check your balance. Please try again."
                }
            
            if current_balance < required_amount:
                return {
                    'valid': False,
                    'message': f"Insufficient balance. Required: {format_bitcoin_amount(required_amount)} BTC, Available: {format_bitcoin_amount(current_balance)} BTC"
                }
            
            return {
                'valid': True,
                'current_balance': current_balance
            }
            
        except Exception as e:
            logger.error(f"Balance check failed for {user.phone_number}: {e}")
            return {
                'valid': False,
                'message': "Unable to verify balance. Please try again."
            }
    
    def _estimate_transaction_fee(self, amount: float) -> float:
        """Estimate transaction fee"""
        try:
            # Try to get actual fee estimate from Bitnob
            fee_result = self.bitnob_service.estimate_fee(amount)
            
            if not fee_result.get('error'):
                fee_data = fee_result.get('data', {})
                return float(fee_data.get('fee', 0.00001))
            
            # Fallback to fixed fee
            return 0.00001  # 1000 satoshis
            
        except Exception as e:
            logger.error(f"Fee estimation failed: {e}")
            return 0.00001  # Safe fallback
    
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
    
    def _get_recipient_name(self, address: str) -> str:
        """Get recipient name for address (placeholder for address book feature)"""
        # TODO: Implement address book lookup
        return "Recipient"
    
    def _format_validation_errors(self, errors: List[str]) -> str:
        """Format validation errors for user display"""
        if len(errors) == 1:
            return f"❌ {errors[0]}"
        
        error_text = "❌ Please fix the following:\n"
        for error in errors:
            error_text += f"• {error}\n"
        
        return error_text.strip()
    
    def _update_transaction_status(self, transaction: Transaction):
        """Update transaction status from Bitnob"""
        try:
            if not transaction.bitnob_transaction_id:
                return
            
            tx_result = self.bitnob_service.get_transaction(transaction.bitnob_transaction_id)
            
            if tx_result.get('error'):
                return
            
            tx_data = tx_result.get('data', {})
            bitnob_status = tx_data.get('status', '').lower()
            
            # Map Bitnob status to our status
            if bitnob_status == 'completed':
                blockchain_hash = tx_data.get('hash')
                transaction.mark_completed(blockchain_hash)
            elif bitnob_status == 'failed':
                failure_reason = tx_data.get('failureReason', 'Transaction failed')
                transaction.mark_failed(failure_reason)
            
        except Exception as e:
            logger.error(f"Status update failed for transaction {transaction.id}: {e}")

def handle_bitnob_webhook(webhook_data: Dict[str, Any], bitnob_service: BitnobService) -> Dict[str, Any]:
    """Handle Bitnob webhook notifications"""
    try:
        event_type = webhook_data.get('event')
        data = webhook_data.get('data', {})
        
        if event_type == 'transaction.completed':
            return _handle_transaction_completed_webhook(data)
        elif event_type == 'transaction.failed':
            return _handle_transaction_failed_webhook(data)
        elif event_type == 'wallet.credited':
            return _handle_wallet_credited_webhook(data)
        else:
            logger.info(f"Unhandled webhook event: {event_type}")
            return {'success': True, 'message': 'Event ignored'}
            
    except Exception as e:
        logger.error(f"Webhook handling failed: {e}")
        return {'success': False, 'error': str(e)}

def _handle_transaction_completed_webhook(data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle transaction completed webhook"""
    try:
        bitnob_tx_id = data.get('id')
        blockchain_hash = data.get('hash')
        
        # Find transaction by Bitnob ID
        transaction = Transaction.query.filter_by(bitnob_transaction_id=bitnob_tx_id).first()
        
        if transaction:
            transaction.mark_completed(blockchain_hash)
            log_user_action(transaction.user.phone_number, "webhook_transaction_completed", 
                          transaction.reference_number)
        
        return {'success': True, 'message': 'Transaction completed webhook processed'}
        
    except Exception as e:
        logger.error(f"Transaction completed webhook failed: {e}")
        return {'success': False, 'error': str(e)}

def _handle_transaction_failed_webhook(data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle transaction failed webhook"""
    try:
        bitnob_tx_id = data.get('id')
        failure_reason = data.get('failureReason', 'Transaction failed')
        
        # Find transaction by Bitnob ID
        transaction = Transaction.query.filter_by(bitnob_transaction_id=bitnob_tx_id).first()
        
        if transaction:
            transaction.mark_failed(failure_reason)
            log_user_action(transaction.user.phone_number, "webhook_transaction_failed", 
                          f"{transaction.reference_number}: {failure_reason}")
        
        return {'success': True, 'message': 'Transaction failed webhook processed'}
        
    except Exception as e:
        logger.error(f"Transaction failed webhook failed: {e}")
        return {'success': False, 'error': str(e)}

def _handle_wallet_credited_webhook(data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle wallet credited webhook (incoming Bitcoin)"""
    try:
        wallet_id = data.get('walletId')
        amount = float(data.get('amount', 0))
        tx_hash = data.get('hash')
        
        # Find user by wallet ID
        user = User.query.filter_by(bitnob_wallet_id=wallet_id).first()
        
        if user and amount > 0:
            # Create receive transaction record
            transaction = Transaction(
                user_id=user.id,
                transaction_type=TransactionType.RECEIVE,
                amount=amount,
                blockchain_hash=tx_hash,
                reference_number=generate_reference_number("RCV"),
                status=TransactionStatus.COMPLETED
            )
            transaction.save()
            
            log_user_action(user.phone_number, "bitcoin_received", 
                          f"{format_bitcoin_amount(amount)} BTC")
        
        return {'success': True, 'message': 'Wallet credited webhook processed'}
        
    except Exception as e:
        logger.error(f"Wallet credited webhook failed: {e}")
        return {'success': False, 'error': str(e)}

# Factory function
def create_transaction_handler(bitnob_service: BitnobService, twilio_service: TwilioService, otp_service: OTPService) -> TransactionHandler:
    """Create transaction handler instance"""
    return TransactionHandler(bitnob_service, twilio_service, otp_service)