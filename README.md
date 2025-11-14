# SatChat - Bitcoin on WhatsApp

## Overview

SatChat is a WhatsApp-based Bitcoin wallet that allows users to send, receive, and manage Bitcoin through conversational messages. Built with Flask, integrated with Bitnob API for Bitcoin operations and Twilio for WhatsApp messaging.

## Features

- 🏦 **Wallet Creation**: Create Bitcoin wallets directly from WhatsApp
- 💸 **Send Bitcoin**: Send BTC via conversational commands
- 📥 **Receive Bitcoin**: Get Bitcoin address for receiving payments
- 🔐 **OTP Security**: Secure transactions with OTP verification
- 📊 **Transaction History**: View recent transactions
- 💰 **Balance Check**: Real-time balance checking
- 🚨 **Error Handling**: Graceful error handling and retry options

## Architecture

```
User → WhatsApp → Twilio → Backend → Bitnob
                            ↓
                        Database (SQLite/PostgreSQL)
```

## Quick Start

### Prerequisites

- Python 3.8+
- Twilio Account with WhatsApp Business API
- Bitnob API Account
- ngrok (for local development)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd SatsPay
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment setup**
   ```bash
   cp .env.example .env
   # Edit .env with your actual credentials
   ```

5. **Initialize database**
   ```bash
   python -c "from app import app; from models.database import init_db; init_db(app)"
   ```

6. **Run the application**
   ```bash
   python app.py
   ```

### Development Setup

1. **Start ngrok** (for webhook testing)
   ```bash
   ngrok http 5000
   ```

2. **Configure Twilio Webhook**
   - Go to Twilio Console → Messaging → WhatsApp Sandbox
   - Set webhook URL: `https://your-ngrok-url.ngrok.io/webhook/twilio`

3. **Configure Bitnob Webhook**
   - Set webhook URL: `https://your-ngrok-url.ngrok.io/webhook/bitnob`

## Configuration

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `SECRET_KEY` | Flask secret key | `your-secret-key` |
| `TWILIO_ACCOUNT_SID` | Twilio Account SID | `AC...` |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token | `your-token` |
| `TWILIO_PHONE_NUMBER` | WhatsApp Business Number | `+1234567890` |
| `BITNOB_API_KEY` | Bitnob API Key | `your-api-key` |
| `BITNOB_SECRET_KEY` | Bitnob Secret Key | `your-secret` |
| `DATABASE_URL` | Database connection URL | `sqlite:///satchat.db` |

### Database Configuration

**Development (SQLite)**
```env
DATABASE_URL=sqlite:///satchat.db
```

**Production (PostgreSQL)**
```env
DATABASE_URL=postgresql://user:password@localhost/satchat
```

## API Endpoints

### Webhooks

- `POST /webhook/twilio` - Receive WhatsApp messages
- `POST /webhook/bitnob` - Receive Bitnob notifications

### API Endpoints

- `GET /health` - Health check
- `GET /api/user/<phone>/balance` - Get user balance
- `GET /api/user/<phone>/transactions` - Get transaction history
- `GET /api/stats` - System statistics

## User Journey

### Registration Flow

1. **Initiate**: User sends "Hi" to WhatsApp bot
2. **Welcome**: Bot responds with welcome message
3. **Confirm**: User replies "YES" to create account
4. **Name**: Bot asks for full name
5. **Email**: Bot asks for email address
6. **Account Creation**: Bot creates Bitnob account and Bitcoin wallet
7. **Complete**: User receives wallet address and balance

### Transaction Flow

1. **Send Command**: "Send 0.001 BTC to 1ABC..."
2. **Validation**: Bot validates amount and address
3. **Confirmation**: Bot shows transaction details
4. **User Confirms**: User replies "YES"
5. **OTP**: Bot sends 6-digit OTP
6. **Authorization**: User enters OTP
7. **Execution**: Bot executes transaction via Bitnob
8. **Result**: Bot sends success/failure message

## Security Features

- 🔐 **OTP Authentication**: All transactions require OTP
- ⏰ **Time-based Expiry**: OTPs expire in 5 minutes
- 🚫 **Rate Limiting**: Prevent brute force attacks
- 🔒 **Account Locking**: Temporary locks after failed attempts
- 🛡️ **Webhook Validation**: Verify webhook signatures
- 📝 **Audit Logging**: Comprehensive action logging

## Deployment

### Production Deployment

1. **Environment Setup**
   ```bash
   export ENVIRONMENT=production
   export DEBUG=False
   # Set all production environment variables
   ```

2. **Database Migration**
   ```bash
   # For PostgreSQL
   python -c "from app import app; from models.database import init_db; init_db(app)"
   ```

3. **Run with Gunicorn**
   ```bash
   gunicorn --bind 0.0.0.0:$PORT app:app
   ```

### Docker Deployment

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
```

### Heroku Deployment

1. **Procfile**
   ```
   web: gunicorn app:app
   ```

2. **Deploy**
   ```bash
   git push heroku main
   heroku config:set TWILIO_ACCOUNT_SID=your_sid
   # Set all environment variables
   ```

## Testing

### Manual Testing

1. **Send WhatsApp Message**: "Hi"
2. **Follow Registration**: Provide name and email
3. **Test Commands**:
   - "Balance" - Check balance
   - "Send 0.001 BTC to [address]" - Send Bitcoin
   - "History" - View transactions
   - "Help" - Get help

### Available Commands

| Command | Description | Example |
|---------|-------------|---------|
| `Hi` | Start registration | `Hi` |
| `Balance` | Check balance | `Balance` |
| `Send` | Send Bitcoin | `Send 0.001 BTC to 1ABC...` |
| `History` | Transaction history | `History` |
| `Address` | Get Bitcoin address | `Address` |
| `Help` | Get help | `Help` |

## Monitoring & Logging

### Log Levels

- **INFO**: Normal operations, user actions
- **WARNING**: Invalid requests, failed validations
- **ERROR**: System errors, API failures
- **DEBUG**: Detailed debugging information

### Metrics to Monitor

- User registrations
- Transaction volume
- Success/failure rates
- API response times
- Error rates

## Troubleshooting

### Common Issues

1. **Webhook not receiving messages**
   - Check ngrok is running
   - Verify Twilio webhook configuration
   - Check webhook signature validation

2. **Bitnob API errors**
   - Verify API credentials
   - Check account limits
   - Review API documentation

3. **Database connection issues**
   - Check DATABASE_URL format
   - Verify database permissions
   - Ensure database exists

4. **OTP delivery issues**
   - Check Twilio account balance
   - Verify phone number format
   - Check SMS/WhatsApp delivery status

## Contributing

1. Fork the repository
2. Create feature branch
3. Make changes
4. Add tests
5. Submit pull request

## License

MIT License - see LICENSE file for details

## Support

For support and questions:
- Email: support@satchat.io
- Documentation: [Link to docs]
- Issues: [GitHub Issues]

## Changelog

### v1.0.0
- Initial release
- WhatsApp integration
- Bitcoin send/receive
- OTP security
- Transaction history
