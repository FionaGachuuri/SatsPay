"""
SatChat MVP - Main Flask Application
Bitcoin on WhatsApp using Twilio and Bitnob API
"""

from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse
import os

# Import configuration
from config import config

# Import database
from models.database import db, init_db, WebhookEvent

# Import handlers
from handlers.commands import command_handler

# Import services
from services.twilio_service import twilio_service

# Import models
from models.user import SessionManager
from services.otp_service import otp_service

# Create Flask app
app = Flask(__name__)

# Load configuration
env = os.environ.get('FLASK_ENV', 'development')
app.config.from_object(config[env])

# Initialize database
db.init_app(app)


# Create tables on first run
@app.before_first_request
def create_tables():
    """Create database tables if they don't exist"""
    try:
        db.create_all()
        print("✅ Database tables created successfully!")
    except Exception as e:
        print(f"❌ Error creating tables: {str(e)}")


# Routes
@app.route('/', methods=['GET'])
def index():
    """Landing page"""
    return """
    <html>
        <head>
            <title>SatChat - Bitcoin on WhatsApp</title>
            <style>
                body {
                    font-family: 'Segoe UI', Arial, sans-serif;
                    max-width: 800px;
                    margin: 50px auto;
                    padding: 20px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                }
                .container {
                    background: rgba(255, 255, 255, 0.95);
                    color: #333;
                    padding: 40px;
                    border-radius: 20px;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                }
                h1 { color: #667eea; margin: 0; }
                h3 { color: #764ba2; margin: 10px 0; }
                .status {
                    display: inline-block;
                    background: #10b981;
                    color: white;
                    padding: 5px 15px;
                    border-radius: 20px;
                    font-size: 14px;
                }
                .command {
                    background: #f3f4f6;
                    padding: 15px;
                    border-radius: 10px;
                    margin: 10px 0;
                    border-left: 4px solid #667eea;
                }
                .command strong {
                    color: #667eea;
                }
                ul {
                    list-style: none;
                    padding: 0;
                }
                li {
                    padding: 8px 0;
                    border-bottom: 1px solid #e5e7eb;
                }
                li:last-child {
                    border-bottom: none;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🚀 SatChat</h1>
                <h3>Bitcoin on WhatsApp</h3>
                <p><span class="status">● Online</span></p>
                
                <hr style="border: none; border-top: 2px solid #e5e7eb; margin: 30px 0;">
                
                <h4>📱 Get Started</h4>
                <div class="command">
                    <p>Send a WhatsApp message to:</p>
                    <p><strong>{}</strong></p>
                    <p>Start with: <strong>HI</strong></p>
                </div>
                
                <h4>📖 Available Commands</h4>
                <ul>
                    <li><strong>HI</strong> - Start or create account</li>
                    <li><strong>BALANCE</strong> - Check your Bitcoin balance</li>
                    <li><strong>SEND &lt;amount&gt; TO &lt;address&gt;</strong> - Send Bitcoin</li>
                    <li><strong>HELP</strong> - Get help</li>
                </ul>
                
                <hr style="border: none; border-top: 2px solid #e5e7eb; margin: 30px 0;">
                
                <p style="text-align: center; color: #6b7280; font-size: 14px;">
                    <em>Secure • Simple • Fast</em>
                </p>
            </div>
        </body>
    </html>
    """.format(app.config.get('TWILIO_WHATSAPP_NUMBER', 'Not configured'))


@app.route('/webhook', methods=['POST'])
def webhook():
    """
    Handle incoming WhatsApp messages from Twilio
    """
    try:
        # Get message data
        incoming_msg = request.values.get('Body', '').strip()
        from_number = request.values.get('From', '').replace('whatsapp:', '')
        
        print(f"📩 Received: '{incoming_msg}' from {from_number}")
        
        # Process message through command handler
        response_text = command_handler.handle_message(from_number, incoming_msg)
        
        # Create Twilio response
        resp = MessagingResponse()
        msg = resp.message()
        msg.body(response_text)
        
        print(f"📤 Response sent to {from_number}")
        
        return str(resp)
    
    except Exception as e:
        print(f"❌ Error in webhook: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Send error response
        resp = MessagingResponse()
        msg = resp.message()
        msg.body("❌ An error occurred. Please try again later or contact support.")
        return str(resp)


@app.route('/webhook/bitnob', methods=['POST'])
def bitnob_webhook():
    """
    Handle webhooks from Bitnob for transaction updates
    """
    try:
        data = request.get_json()
        
        # Log webhook event
        event = WebhookEvent(
            event_type=data.get('event', 'unknown'),
            event_source='bitnob',
            payload=data,
            is_verified=True,  # Add signature verification in production
            processed=False
        )
        db.session.add(event)
        db.session.commit()
        
        # Process event
        event_type = data.get('event')
        transaction = data.get('data', {})
        
        if event_type == 'transaction.success':
            customer_phone = transaction.get('customerPhone')
            if customer_phone:
                message = (
                    f"✅ *Transaction Confirmed!*\n\n"
                    f"Reference: {transaction.get('reference')}\n"
                    f"Status: Completed"
                )
                twilio_service.send_message(customer_phone, message)
        
        elif event_type == 'transaction.failed':
            customer_phone = transaction.get('customerPhone')
            if customer_phone:
                message = (
                    f"❌ *Transaction Failed*\n\n"
                    f"Reference: {transaction.get('reference')}\n"
                    f"Reason: {transaction.get('failureReason', 'Unknown')}"
                )
                twilio_service.send_message(customer_phone, message)
        
        # Mark as processed
        event.processed = True
        db.session.commit()
        
        return jsonify({'status': 'success'}), 200
    
    except Exception as e:
        print(f"❌ Error in Bitnob webhook: {str(e)}")
        return jsonify({'error': 'Internal error'}), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    try:
        # Check database connection
        db.session.execute('SELECT 1')
        
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@app.route('/api/stats', methods=['GET'])
def stats():
    """Basic statistics endpoint"""
    try:
        from models.database import User, Transaction
        
        total_users = User.query.count()
        total_transactions = Transaction.query.count()
        pending_transactions = Transaction.query.filter_by(status='pending').count()
        
        return jsonify({
            'total_users': total_users,
            'total_transactions': total_transactions,
            'pending_transactions': pending_transactions,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Cleanup task (run periodically via scheduler)
@app.route('/admin/cleanup', methods=['POST'])
def cleanup():
    """
    Cleanup expired sessions and OTPs
    Protect this endpoint in production!
    """
    try:
        # Add authentication here in production
        auth_token = request.headers.get('X-Admin-Token')
        if auth_token != os.environ.get('ADMIN_TOKEN'):
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Cleanup expired sessions
        SessionManager.cleanup_expired_sessions()
        
        # Cleanup expired OTPs
        otp_service.cleanup_expired_otps()
        
        return jsonify({
            'status': 'success',
            'message': 'Cleanup completed'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return jsonify({'error': 'Internal server error'}), 500


# Import datetime for health check
from datetime import datetime


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    # Create tables if they don't exist
    with app.app_context():
        try:
            db.create_all()
            print("✅ Database initialized successfully!")
        except Exception as e:
            print(f"❌ Database initialization error: {str(e)}")
    
    print(f"🚀 SatChat MVP starting on port {port}")
    print(f"📱 WhatsApp Number: {app.config.get('TWILIO_WHATSAPP_NUMBER')}")
    print(f"🗄️  Database: {app.config.get('MYSQL_DATABASE')}")
    
    app.run(host='0.0.0.0', port=port, debug=app.config.get('DEBUG', False))