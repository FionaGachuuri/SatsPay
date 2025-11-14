from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class TwilioService:
    def __init__(self, account_sid: str, auth_token: str, phone_number: str):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.phone_number = phone_number
        self.client = Client(account_sid, auth_token)
        self.validator = RequestValidator(auth_token)
    
    def send_message(self, to_number: str, message: str) -> Dict[str, Any]:
        """Send WhatsApp message"""
        try:
            # Format phone numbers for WhatsApp
            from_whatsapp = f"whatsapp:{self.phone_number}"
            to_whatsapp = f"whatsapp:{to_number}"
            
            message_instance = self.client.messages.create(
                body=message,
                from_=from_whatsapp,
                to=to_whatsapp
            )
            
            logger.info(f"WhatsApp message sent to {to_number}, SID: {message_instance.sid}")
            return {
                'success': True,
                'message_sid': message_instance.sid,
                'status': message_instance.status
            }
            
        except Exception as e:
            logger.error(f"Failed to send WhatsApp message to {to_number}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def send_sms(self, to_number: str, message: str) -> Dict[str, Any]:
        """Send SMS message (fallback)"""
        try:
            message_instance = self.client.messages.create(
                body=message,
                from_=self.phone_number,
                to=to_number
            )
            
            logger.info(f"SMS sent to {to_number}, SID: {message_instance.sid}")
            return {
                'success': True,
                'message_sid': message_instance.sid,
                'status': message_instance.status
            }
            
        except Exception as e:
            logger.error(f"Failed to send SMS to {to_number}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def send_otp(self, to_number: str, otp_code: str, purpose: str = "transaction") -> Dict[str, Any]:
        """Send OTP via WhatsApp with SMS fallback"""
        otp_message = self._format_otp_message(otp_code, purpose)
        
        # Try WhatsApp first
        whatsapp_result = self.send_message(to_number, otp_message)
        
        if whatsapp_result['success']:
            return whatsapp_result
        
        # Fallback to SMS
        logger.info(f"WhatsApp failed, trying SMS for {to_number}")
        sms_result = self.send_sms(to_number, otp_message)
        sms_result['fallback_used'] = True
        
        return sms_result
    
    def _format_otp_message(self, otp_code: str, purpose: str) -> str:
        """Format OTP message"""
        purpose_text = {
            'transaction': 'transaction authorization',
            'registration': 'account registration',
            'login': 'login verification',
            'reset_pin': 'PIN reset'
        }.get(purpose, 'verification')
        
        return f"""🔐 SatChat Security Code

Your {purpose_text} code is: *{otp_code}*

⚠️ This code expires in 5 minutes
⚠️ Do not share this code with anyone

Need help? Reply HELP"""
    
    def create_twiml_response(self, message: str) -> str:
        """Create TwiML response for webhook"""
        response = MessagingResponse()
        response.message(message)
        return str(response)
    
    def validate_webhook(self, url: str, params: Dict, signature: str) -> bool:
        """Validate Twilio webhook signature"""
        try:
            return self.validator.validate(url, params, signature)
        except Exception as e:
            logger.error(f"Webhook validation failed: {e}")
            return False
    
    def get_message_status(self, message_sid: str) -> Dict[str, Any]:
        """Get message delivery status"""
        try:
            message = self.client.messages(message_sid).fetch()
            return {
                'sid': message.sid,
                'status': message.status,
                'error_code': message.error_code,
                'error_message': message.error_message
            }
        except Exception as e:
            logger.error(f"Failed to get message status for {message_sid}: {e}")
            return {'error': str(e)}

class MessageFormatter:
    """Helper class for formatting WhatsApp messages"""
    
    @staticmethod
    def welcome_message() -> str:
        return """🚀 *Welcome to SatChat!*

Bitcoin in your pocket, on WhatsApp.

I can help you:
• 🏦 Create a Bitcoin wallet
• 💸 Send Bitcoin to anyone
• 📥 Receive Bitcoin payments
• 💰 Check your balance
• 📊 View transaction history

Ready to get started? Reply *YES* to create your account or *HELP* for assistance."""
    
    @staticmethod
    def account_created_message(bitcoin_address: str, balance: str = "0.00000000") -> str:
        return f"""✅ *Account Created Successfully!*

Your Bitcoin wallet is ready:
🔗 Address: `{bitcoin_address}`
💰 Balance: {balance} BTC

You can now:
• Send BTC: "Send 0.001 BTC to [address]"
• Check balance: "Balance"
• Get help: "Help"

*Your wallet is secured with OTP verification for all transactions.*"""
    
    @staticmethod
    def transaction_confirmation(amount: str, recipient: str, address: str, reference: str, fee: str = None) -> str:
        fee_text = f"\n💳 Network Fee: {fee} BTC" if fee else ""
        
        return f"""🔍 *Transaction Confirmation*

You are about to send:
💰 Amount: {amount} BTC
👤 To: {recipient}
🔗 Address: `{address}`
📋 Reference: {reference}{fee_text}

⚠️ Please verify the details carefully.

Reply *YES* to confirm or *NO* to cancel."""
    
    @staticmethod
    def otp_prompt() -> str:
        return """🔐 *Security Verification Required*

An OTP has been sent to authorize this transaction.

Please enter the 6-digit code to proceed.

⏰ Code expires in 5 minutes"""
    
    @staticmethod
    def transaction_success(amount: str, recipient: str, reference: str, new_balance: str, tx_hash: str = None) -> str:
        hash_text = f"\n🔗 Blockchain: `{tx_hash}`" if tx_hash else ""
        
        return f"""✅ *Transaction Successful!*

💰 Sent: {amount} BTC
👤 To: {recipient}
📋 Reference: {reference}
💳 New Balance: {new_balance} BTC{hash_text}

Transaction completed successfully! 🎉"""
    
    @staticmethod
    def transaction_failed(reason: str) -> str:
        return f"""❌ *Transaction Failed*

{reason}

Please try again or contact support if the issue persists.

Need help? Reply *HELP*"""
    
    @staticmethod
    def balance_message(balance: str, address: str) -> str:
        return f"""💰 *Your Bitcoin Balance*

Balance: {balance} BTC
Address: `{address}`

To receive Bitcoin, share your address with the sender.
To send Bitcoin, use: "Send [amount] BTC to [address]" """
    
    @staticmethod
    def help_message() -> str:
        return """🆘 *SatChat Help*

*Available Commands:*
• Send 0.001 BTC to [address] - Send Bitcoin
• Balance - Check your balance
• History - View recent transactions
• Address - Get your Bitcoin address
• Help - Show this help message

*Transaction Security:*
• All transactions require OTP verification
• OTPs expire in 5 minutes
• Never share your OTP with anyone

*Need Support?*
Contact us at support@satchat.io"""
    
    @staticmethod
    def error_message(message: str = "Something went wrong") -> str:
        return f"""⚠️ *Error*

{message}

Please try again or reply *HELP* for assistance."""
    
    @staticmethod
    def invalid_command_message() -> str:
        return """❓ *Invalid Command*

I didn't understand that command.

Try:
• "Balance" - Check your balance
• "Send 0.001 BTC to [address]" - Send Bitcoin
• "Help" - Get help

Reply *HELP* for more options."""

# Factory function
def create_twilio_service(account_sid: str, auth_token: str, phone_number: str) -> TwilioService:
    """Create Twilio service instance"""
    return TwilioService(account_sid, auth_token, phone_number)