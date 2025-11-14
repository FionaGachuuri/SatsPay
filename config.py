import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Flask configuration
    SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-here')
    
    # Database configuration
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///satchat.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Twilio configuration
    TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
    TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
    TWILIO_WEBHOOK_URL = os.getenv('TWILIO_WEBHOOK_URL')
    
    # Bitnob API configuration
    BITNOB_API_KEY = os.getenv('BITNOB_API_KEY')
    BITNOB_SECRET_KEY = os.getenv('BITNOB_SECRET_KEY')
    BITNOB_BASE_URL = os.getenv('BITNOB_BASE_URL', 'https://api.bitnob.co')
    BITNOB_WEBHOOK_SECRET = os.getenv('BITNOB_WEBHOOK_SECRET')
    
    # OTP configuration
    OTP_EXPIRY_MINUTES = int(os.getenv('OTP_EXPIRY_MINUTES', '5'))
    MAX_OTP_ATTEMPTS = int(os.getenv('MAX_OTP_ATTEMPTS', '3'))
    
    # Rate limiting
    RATE_LIMIT_PER_MINUTE = int(os.getenv('RATE_LIMIT_PER_MINUTE', '10'))
    
    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    
    # Environment
    ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

config_dict = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig
}

def get_config():
    return config_dict.get(os.getenv('ENVIRONMENT', 'development'), DevelopmentConfig)