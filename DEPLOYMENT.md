# SatsPay Deployment Guide

This guide provides comprehensive instructions for deploying the SatsPay application across different environments.

## Table of Contents
- [Prerequisites](#prerequisites)
- [Environment Setup](#environment-setup)
- [Local Development](#local-development)
- [Production Deployment](#production-deployment)
- [Docker Deployment](#docker-deployment)
- [Heroku Deployment](#heroku-deployment)
- [Environment Variables](#environment-variables)
- [Database Setup](#database-setup)
- [Monitoring and Logging](#monitoring-and-logging)
- [Troubleshooting](#troubleshooting)

## Prerequisites

Before deploying SatsPay, ensure you have:

- Python 3.10 or higher
- PostgreSQL database
- Twilio account (for SMS OTP)
- Bitnob account (for Bitcoin transactions)
- Git
- Docker (optional, for containerized deployment)

## Environment Setup

### 1. Clone the Repository

```bash
git clone https://github.com/FionaGachuuri/SatsPay.git
cd SatsPay
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

## Local Development

### 1. Environment Variables

Create a `.env` file in the root directory:

```env
# Flask Configuration
FLASK_APP=app.py
FLASK_ENV=development
SECRET_KEY=your_secret_key_here
DEBUG=True
PORT=5000

# Database
DATABASE_URL=postgresql://user:password@localhost/satchat

# Twilio Configuration
TWILIO_ACCOUNT_SID=your_twilio_account_sid_here
TWILIO_AUTH_TOKEN=your_twilio_auth_token_here
TWILIO_PHONE_NUMBER=+1234567890
TWILIO_WEBHOOK_URL=https://your-domain.com/webhook/twilio

# Bitnob Configuration
BITNOB_API_KEY=your_bitnob_api_key_here
BITNOB_SECRET_KEY=your_bitnob_secret_key_here
BITNOB_BASE_URL=https://api.bitnob.co
BITNOB_WEBHOOK_SECRET=your_webhook_secret_here

# OTP Configuration
OTP_EXPIRY_MINUTES=5
MAX_OTP_ATTEMPTS=3
```

### 2. Database Setup

```bash
# Initialize the database
python init_db.py

# Or run the initialization script
python -c "from models.database import init_db; init_db()"
```

### 3. Run the Application

```bash
python app.py
```

The application will be available at `http://localhost:5000`

## Production Deployment

### 1. Server Setup

For production deployment on a Linux server:

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install Python and PostgreSQL
sudo apt install python3.10 python3.10-venv python3-pip postgresql postgresql-contrib nginx -y

# Create application user
sudo useradd -m -s /bin/bash satchat
sudo su - satchat
```

### 2. Application Setup

```bash
# Clone repository
git clone https://github.com/FionaGachuuri/SatsPay.git
cd SatsPay

# Create virtual environment
python3.10 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install gunicorn
```

### 3. Database Configuration

```bash
# Switch to postgres user
sudo su - postgres

# Create database and user
createdb satchat
createuser --interactive satchat

# Grant privileges
psql -c "ALTER USER satchat WITH PASSWORD 'your_secure_password';"
psql -c "GRANT ALL PRIVILEGES ON DATABASE satchat TO satchat;"
```

### 4. Environment Variables

Create `/home/satchat/SatsPay/.env`:

```env
FLASK_APP=app.py
FLASK_ENV=production
SECRET_KEY=your_production_secret_key_here
DEBUG=False
PORT=5000

DATABASE_URL=postgresql://satchat:your_secure_password@localhost/satchat

TWILIO_ACCOUNT_SID=your_actual_twilio_account_sid
TWILIO_AUTH_TOKEN=your_actual_twilio_auth_token
TWILIO_PHONE_NUMBER=your_actual_twilio_phone_number
TWILIO_WEBHOOK_URL=https://your-production-domain.com/webhook/twilio

BITNOB_API_KEY=your_actual_bitnob_api_key
BITNOB_SECRET_KEY=your_actual_bitnob_secret_key
BITNOB_BASE_URL=https://api.bitnob.co
BITNOB_WEBHOOK_SECRET=your_actual_webhook_secret

OTP_EXPIRY_MINUTES=5
MAX_OTP_ATTEMPTS=3
```

### 5. Initialize Database

```bash
source venv/bin/activate
python init_db.py
```

### 6. Create Systemd Service

Create `/etc/systemd/system/satchat.service`:

```ini
[Unit]
Description=SatsPay Gunicorn instance
After=network.target

[Service]
User=satchat
Group=satchat
WorkingDirectory=/home/satchat/SatsPay
Environment="PATH=/home/satchat/SatsPay/venv/bin"
EnvironmentFile=/home/satchat/SatsPay/.env
ExecStart=/home/satchat/SatsPay/venv/bin/gunicorn --workers 3 --bind unix:satchat.sock -m 007 app:app
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

### 7. Configure Nginx

Create `/etc/nginx/sites-available/satchat`:

```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;

    location / {
        include proxy_params;
        proxy_pass http://unix:/home/satchat/SatsPay/satchat.sock;
    }

    # Static files
    location /static {
        alias /home/satchat/SatsPay/static;
    }
}
```

Enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/satchat /etc/nginx/sites-enabled
sudo nginx -t
sudo systemctl restart nginx
```

### 8. Start Services

```bash
sudo systemctl daemon-reload
sudo systemctl start satchat
sudo systemctl enable satchat
sudo systemctl status satchat
```

## Docker Deployment

### 1. Build Docker Image

```bash
docker build -t satchat:latest .
```

### 2. Run with Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  web:
    build: .
    ports:
      - "5000:5000"
    environment:
      - DATABASE_URL=postgresql://postgres:password@db:5432/satchat
      - TWILIO_ACCOUNT_SID=your_twilio_account_sid_here
      - TWILIO_AUTH_TOKEN=your_twilio_auth_token_here
      - BITNOB_API_KEY=your_bitnob_api_key_here
      - BITNOB_SECRET_KEY=your_bitnob_secret_key_here
    depends_on:
      - db
    volumes:
      - ./instance:/app/instance

  db:
    image: postgres:13
    environment:
      - POSTGRES_DB=satchat
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

volumes:
  postgres_data:
```

Run the application:

```bash
docker-compose up -d
```

## Heroku Deployment

### 1. Install Heroku CLI

```bash
# Install Heroku CLI (Ubuntu/Debian)
curl https://cli-assets.heroku.com/install-ubuntu.sh | sh

# Login to Heroku
heroku login
```

### 2. Create Heroku App

```bash
heroku create your-app-name
```

### 3. Add PostgreSQL Add-on

```bash
heroku addons:create heroku-postgresql:hobby-dev
```

### 4. Set Environment Variables

```bash
heroku config:set FLASK_APP=app.py
heroku config:set FLASK_ENV=production
heroku config:set SECRET_KEY=your_production_secret_key
heroku config:set TWILIO_ACCOUNT_SID=your_twilio_account_sid
heroku config:set TWILIO_AUTH_TOKEN=your_twilio_auth_token
heroku config:set TWILIO_PHONE_NUMBER=your_twilio_phone_number
heroku config:set BITNOB_API_KEY=your_bitnob_api_key
heroku config:set BITNOB_SECRET_KEY=your_bitnob_secret_key
heroku config:set BITNOB_BASE_URL=https://api.bitnob.co
```

### 5. Deploy

```bash
git push heroku main
```

### 6. Initialize Database

```bash
heroku run python init_db.py
```

## Environment Variables

### Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `SECRET_KEY` | Flask secret key for sessions | `your-secret-key-here` |
| `DATABASE_URL` | PostgreSQL database URL | `postgresql://user:pass@localhost/db` |
| `TWILIO_ACCOUNT_SID` | Twilio Account SID | `your_twilio_account_sid_here` |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token | `your_twilio_auth_token_here` |
| `TWILIO_PHONE_NUMBER` | Twilio Phone Number | `+1234567890` |
| `BITNOB_API_KEY` | Bitnob API Key | `your_bitnob_api_key_here` |
| `BITNOB_SECRET_KEY` | Bitnob Secret Key | `your_bitnob_secret_key_here` |

### Optional Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `FLASK_ENV` | Flask environment | `development` |
| `DEBUG` | Enable debug mode | `False` |
| `PORT` | Port number | `5000` |
| `OTP_EXPIRY_MINUTES` | OTP expiry time | `5` |
| `MAX_OTP_ATTEMPTS` | Maximum OTP attempts | `3` |

## Database Setup

### Local PostgreSQL Setup

1. Install PostgreSQL:
```bash
# Ubuntu/Debian
sudo apt install postgresql postgresql-contrib

# macOS
brew install postgresql
```

2. Create database:
```bash
sudo -u postgres psql
CREATE DATABASE satchat;
CREATE USER satchat WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE satchat TO satchat;
\q
```

3. Update DATABASE_URL in your `.env` file:
```env
DATABASE_URL=postgresql://satchat:your_password@localhost/satchat
```

### Database Migrations

If you make changes to the database schema, run:

```bash
python init_db.py
```

## Monitoring and Logging

### Application Logs

Logs are written to:
- Development: Console output
- Production: `/var/log/satchat/app.log` (configure in your systemd service)

### Health Check Endpoint

The application provides a health check endpoint:

```
GET /health
```

Returns:
```json
{
    "status": "healthy",
    "timestamp": "2023-12-07T10:30:00Z",
    "database": "connected"
}
```

### Monitoring with Uptime Checks

Set up monitoring with services like:
- UptimeRobot
- Pingdom
- New Relic
- DataDog

## SSL/HTTPS Configuration

### Using Let's Encrypt with Certbot

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx

# Obtain SSL certificate
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# Auto-renewal
sudo crontab -e
# Add: 0 12 * * * /usr/bin/certbot renew --quiet
```

Update your Nginx configuration to redirect HTTP to HTTPS.

## Backup and Recovery

### Database Backup

```bash
# Create backup
pg_dump -h localhost -U satchat satchat > backup_$(date +%Y%m%d_%H%M%S).sql

# Restore backup
psql -h localhost -U satchat satchat < backup_20231207_103000.sql
```

### Automated Backups

Create a backup script and add it to cron:

```bash
#!/bin/bash
BACKUP_DIR="/home/satchat/backups"
DATE=$(date +%Y%m%d_%H%M%S)
pg_dump -h localhost -U satchat satchat > "$BACKUP_DIR/satchat_$DATE.sql"
find "$BACKUP_DIR" -name "satchat_*.sql" -mtime +7 -delete
```

## Troubleshooting

### Common Issues

1. **Database Connection Error**
   - Check DATABASE_URL format
   - Verify database is running
   - Check user permissions

2. **Twilio SMS Not Working**
   - Verify TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN
   - Check phone number format
   - Ensure Twilio account has sufficient balance

3. **Bitnob API Errors**
   - Verify API credentials
   - Check API endpoint availability
   - Review API rate limits

4. **Application Won't Start**
   - Check Python version compatibility
   - Verify all dependencies are installed
   - Review application logs

### Debug Mode

Enable debug mode for development:

```env
DEBUG=True
FLASK_ENV=development
```

**Never enable debug mode in production!**

### Log Analysis

Check application logs:

```bash
# Systemd service logs
sudo journalctl -u satchat -f

# Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log

# Application logs (if configured)
tail -f /var/log/satchat/app.log
```

## Security Considerations

1. **Environment Variables**: Never commit `.env` files to version control
2. **Secret Keys**: Use strong, randomly generated secret keys
3. **Database**: Use strong passwords and limit access
4. **HTTPS**: Always use HTTPS in production
5. **Firewall**: Configure firewall to only allow necessary ports
6. **Updates**: Keep dependencies and system packages updated
7. **Monitoring**: Set up log monitoring and alerting

## Performance Optimization

1. **Database Indexing**: Add indexes to frequently queried columns
2. **Connection Pooling**: Use connection pooling for database connections
3. **Caching**: Implement Redis caching for frequently accessed data
4. **CDN**: Use CDN for static assets
5. **Load Balancing**: Use multiple application instances behind a load balancer

## Support and Maintenance

For ongoing support:

1. Monitor application logs regularly
2. Set up automated backups
3. Keep dependencies updated
4. Monitor resource usage
5. Test disaster recovery procedures

## Additional Resources

- [Flask Documentation](https://flask.palletsprojects.com/)
- [Gunicorn Documentation](https://docs.gunicorn.org/)
- [Nginx Documentation](https://nginx.org/en/docs/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Twilio Documentation](https://www.twilio.com/docs)
- [Bitnob API Documentation](https://docs.bitnob.co/)

---

For questions or issues, please refer to the project's GitHub repository or contact the development team.
