from flask import Flask, request, jsonify
import logging
import os
from datetime import datetime

# Local imports
from config import get_config
from models.database import init_db
from models.user import get_user_by_phone
from services.bitnob_service import BitnobService
from services.twilio_service import TwilioService, create_twilio_service
from services.otp_service import create_otp_service
from handlers.commands import create_command_handler
from handlers.registration import create_registration_handler
from handlers.transaction import create_transaction_handler, handle_bitnob_webhook
from utils.helpers import normalize_phone_number, log_user_action
from utils.validators import MessageValidator

# Initialize Flask app
app = Flask(__name__)

# Load configuration
config = get_config()
app.config.from_object(config)

# Initialize database
init_db(app)

# Configure logging
logging.basicConfig(
    level=getattr(logging, app.config['LOG_LEVEL']),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize services
bitnob_service = BitnobService(
    api_key=app.config['BITNOB_API_KEY'],
    secret_key=app.config['BITNOB_SECRET_KEY'],
    base_url=app.config['BITNOB_BASE_URL']
)

twilio_service = create_twilio_service(
    account_sid=app.config['TWILIO_ACCOUNT_SID'],
    auth_token=app.config['TWILIO_AUTH_TOKEN'],
    phone_number=app.config['TWILIO_PHONE_NUMBER']
)

otp_service = create_otp_service(
    expiry_minutes=app.config['OTP_EXPIRY_MINUTES'],
    max_attempts=app.config['MAX_OTP_ATTEMPTS']
)

# Initialize handlers
command_handler = create_command_handler(bitnob_service, twilio_service, otp_service)
registration_handler = create_registration_handler(bitnob_service, twilio_service, otp_service)
transaction_handler = create_transaction_handler(bitnob_service, twilio_service, otp_service)

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'version': '1.0.0'
    })

@app.route('/webhook/twilio', methods=['POST'])
def twilio_webhook():
    """Handle incoming WhatsApp messages from Twilio"""
    try:
        # Validate webhook signature in production
        if app.config['ENVIRONMENT'] == 'production':
            if not _validate_twilio_webhook():
                logger.warning("Invalid Twilio webhook signature")
                return "Unauthorized", 401
        
        # Extract message data
        from_number = request.form.get('From', '').replace('whatsapp:', '')
        message_body = request.form.get('Body', '').strip()
        
        if not from_number or not message_body:
            logger.warning("Invalid webhook data received")
            return "Bad Request", 400
        
        # Validate message content
        message_validation = MessageValidator.validate_message_content(message_body)
        if not message_validation['valid']:
            logger.warning(f"Invalid message content from {from_number}")
            response_message = "Invalid message format. Please try again."
        else:
            # Process the message
            response_message = command_handler.handle_message(from_number, message_body)
        
        # Return TwiML response
        twiml_response = twilio_service.create_twiml_response(response_message)
        
        return twiml_response, 200, {'Content-Type': 'text/xml'}
        
    except Exception as e:
        logger.error(f"Twilio webhook error: {e}")
        error_response = twilio_service.create_twiml_response(
            "Sorry, something went wrong. Please try again later."
        )
        return error_response, 500, {'Content-Type': 'text/xml'}

@app.route('/webhook/bitnob', methods=['POST'])
def bitnob_webhook():
    """Handle Bitnob webhook notifications"""
    try:
        # Validate webhook signature in production
        if app.config['ENVIRONMENT'] == 'production':
            if not _validate_bitnob_webhook():
                logger.warning("Invalid Bitnob webhook signature")
                return jsonify({'error': 'Unauthorized'}), 401
        
        webhook_data = request.get_json()
        
        if not webhook_data:
            logger.warning("Empty Bitnob webhook data")
            return jsonify({'error': 'Bad Request'}), 400
        
        # Process webhook
        result = handle_bitnob_webhook(webhook_data, bitnob_service)
        
        if result['success']:
            return jsonify({'status': 'processed'}), 200
        else:
            logger.error(f"Bitnob webhook processing failed: {result}")
            return jsonify({'error': 'Processing failed'}), 500
            
    except Exception as e:
        logger.error(f"Bitnob webhook error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/user/<phone_number>/balance', methods=['GET'])
def get_user_balance_api(phone_number):
    """API endpoint to get user balance"""
    try:
        # This endpoint could be used by admin interfaces or monitoring
        # Add authentication/authorization as needed
        
        normalized_phone = normalize_phone_number(phone_number)
        user = get_user_by_phone(normalized_phone)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        if not user.is_kyc_completed:
            return jsonify({'error': 'User account not complete'}), 400
        
        # Get balance via Bitnob
        balance_result = bitnob_service.get_wallet_balance(user.bitnob_wallet_id)
        
        if balance_result.get('error'):
            return jsonify({'error': 'Failed to get balance'}), 500
        
        balance_data = balance_result.get('data', {})
        
        return jsonify({
            'phone_number': normalized_phone,
            'balance': float(balance_data.get('available', 0)),
            'currency': 'BTC',
            'wallet_address': user.bitcoin_address,
            'updated_at': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Get balance API error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/user/<phone_number>/transactions', methods=['GET'])
def get_user_transactions_api(phone_number):
    """API endpoint to get user transactions"""
    try:
        normalized_phone = normalize_phone_number(phone_number)
        user = get_user_by_phone(normalized_phone)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get transaction history
        result = transaction_handler.get_transaction_history(user)
        
        if result['success']:
            return jsonify({
                'phone_number': normalized_phone,
                'transactions': result['transactions'],
                'count': len(result['transactions'])
            })
        else:
            return jsonify({'error': result.get('message', 'Failed to get transactions')}), 500
            
    except Exception as e:
        logger.error(f"Get transactions API error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get system statistics"""
    try:
        from models.user import User, Transaction
        
        total_users = User.query.count()
        active_users = User.query.filter_by(is_kyc_completed=True).count()
        total_transactions = Transaction.query.count()
        
        return jsonify({
            'total_users': total_users,
            'active_users': active_users,
            'total_transactions': total_transactions,
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Get stats error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

def _validate_twilio_webhook():
    """Validate Twilio webhook signature"""
    try:
        signature = request.headers.get('X-Twilio-Signature', '')
        url = request.url
        
        return twilio_service.validate_webhook(url, request.form, signature)
        
    except Exception as e:
        logger.error(f"Twilio webhook validation error: {e}")
        return False

def _validate_bitnob_webhook():
    """Validate Bitnob webhook signature"""
    try:
        signature = request.headers.get('X-Bitnob-Signature', '')
        payload = request.get_data(as_text=True)
        
        return bitnob_service.verify_webhook(payload, signature)
        
    except Exception as e:
        logger.error(f"Bitnob webhook validation error: {e}")
        return False

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({'error': 'Internal server error'}), 500

@app.before_request
def log_request():
    """Log incoming requests"""
    if request.endpoint != 'health_check':
        logger.info(f"{request.method} {request.path} from {request.remote_addr}")

@app.after_request
def after_request(response):
    """Log response and add security headers"""
    # Add security headers
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    
    if app.config['ENVIRONMENT'] == 'production':
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    
    return response

if __name__ == '__main__':
    # Development server
    if app.config['ENVIRONMENT'] == 'development':
        app.run(
            host='0.0.0.0',
            port=int(os.getenv('PORT', 5000)),
            debug=app.config['DEBUG']
        )
    else:
        # Production should use a proper WSGI server like Gunicorn
        logger.info("Use a production WSGI server like Gunicorn for production deployment")
        app.run(
            host='0.0.0.0',
            port=int(os.getenv('PORT', 5000)),
            debug=False
        )