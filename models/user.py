from datetime import datetime, timedelta
from .database import db, BaseModel
import enum

class UserStatus(enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    BLOCKED = "blocked"

class TransactionStatus(enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TransactionType(enum.Enum):
    SEND = "send"
    RECEIVE = "receive"
    BUY = "buy"
    SELL = "sell"

class User(BaseModel):
    __tablename__ = 'users'
    
    # Personal information
    phone_number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    
    # Account status
    status = db.Column(db.Enum(UserStatus), default=UserStatus.PENDING, nullable=False)
    is_kyc_completed = db.Column(db.Boolean, default=False)
    
    # Bitnob integration
    bitnob_customer_id = db.Column(db.String(100), nullable=True)
    bitnob_wallet_id = db.Column(db.String(100), nullable=True)
    bitcoin_address = db.Column(db.String(100), nullable=True)
    
    # Security
    failed_otp_attempts = db.Column(db.Integer, default=0)
    last_failed_otp = db.Column(db.DateTime, nullable=True)
    is_locked = db.Column(db.Boolean, default=False)
    locked_until = db.Column(db.DateTime, nullable=True)
    
    # Session management
    current_session_state = db.Column(db.String(50), nullable=True)
    session_data = db.Column(db.Text, nullable=True)  # JSON string
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    transactions = db.relationship('Transaction', backref='user', lazy='dynamic')
    otps = db.relationship('OTP', backref='user', lazy='dynamic')
    
    def __repr__(self):
        return f'<User {self.phone_number}>'
    
    @property
    def is_account_locked(self):
        """Check if account is temporarily locked"""
        if not self.is_locked:
            return False
        if self.locked_until and datetime.utcnow() > self.locked_until:
            self.is_locked = False
            self.locked_until = None
            self.failed_otp_attempts = 0
            self.save()
            return False
        return True
    
    def lock_account(self, duration_minutes=30):
        """Lock account for specified duration"""
        self.is_locked = True
        self.locked_until = datetime.utcnow() + timedelta(minutes=duration_minutes)
        self.save()
    
    def increment_failed_otp(self):
        """Increment failed OTP attempts and lock if needed"""
        self.failed_otp_attempts += 1
        self.last_failed_otp = datetime.utcnow()
        
        if self.failed_otp_attempts >= 3:
            self.lock_account(30)  # Lock for 30 minutes
        
        self.save()
    
    def reset_failed_otp(self):
        """Reset failed OTP attempts after successful verification"""
        self.failed_otp_attempts = 0
        self.last_failed_otp = None
        self.save()
    
    def update_session(self, state, data=None):
        """Update user session state"""
        self.current_session_state = state
        self.session_data = data
        self.last_activity = datetime.utcnow()
        self.save()
    
    def clear_session(self):
        """Clear user session"""
        self.current_session_state = None
        self.session_data = None
        self.save()

class Transaction(BaseModel):
    __tablename__ = 'transactions'
    
    # User relationship
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    
    # Transaction details
    transaction_type = db.Column(db.Enum(TransactionType), nullable=False)
    amount = db.Column(db.Numeric(precision=18, scale=8), nullable=False)
    currency = db.Column(db.String(10), default='BTC', nullable=False)
    
    # Recipient/Sender details
    recipient_address = db.Column(db.String(100), nullable=True)
    recipient_name = db.Column(db.String(100), nullable=True)
    sender_address = db.Column(db.String(100), nullable=True)
    
    # Transaction status and tracking
    status = db.Column(db.Enum(TransactionStatus), default=TransactionStatus.PENDING)
    bitnob_transaction_id = db.Column(db.String(100), nullable=True)
    blockchain_hash = db.Column(db.String(100), nullable=True)
    reference_number = db.Column(db.String(50), nullable=False, unique=True)
    
    # Additional details
    description = db.Column(db.Text, nullable=True)
    fee = db.Column(db.Numeric(precision=18, scale=8), nullable=True)
    exchange_rate = db.Column(db.Numeric(precision=18, scale=8), nullable=True)
    
    # Timestamps
    initiated_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    def __repr__(self):
        return f'<Transaction {self.reference_number}>'
    
    def mark_completed(self, blockchain_hash=None):
        """Mark transaction as completed"""
        self.status = TransactionStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        if blockchain_hash:
            self.blockchain_hash = blockchain_hash
        self.save()
    
    def mark_failed(self, reason=None):
        """Mark transaction as failed"""
        self.status = TransactionStatus.FAILED
        if reason:
            self.description = f"{self.description or ''}\nFailure reason: {reason}"
        self.save()

class OTP(BaseModel):
    __tablename__ = 'otps'
    
    # User relationship
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    
    # OTP details
    code = db.Column(db.String(10), nullable=False)
    purpose = db.Column(db.String(50), nullable=False)  # 'transaction', 'registration', etc.
    is_used = db.Column(db.Boolean, default=False)
    attempts = db.Column(db.Integer, default=0)
    max_attempts = db.Column(db.Integer, default=3)
    
    # Expiry
    expires_at = db.Column(db.DateTime, nullable=False)
    
    # Related transaction (if applicable)
    transaction_id = db.Column(db.String(36), db.ForeignKey('transactions.id'), nullable=True)
    transaction = db.relationship('Transaction', backref='otps')
    
    def __repr__(self):
        return f'<OTP {self.code} for {self.user.phone_number}>'
    
    @property
    def is_expired(self):
        """Check if OTP is expired"""
        return datetime.utcnow() > self.expires_at
    
    @property
    def is_valid(self):
        """Check if OTP is valid (not used, not expired, attempts not exceeded)"""
        return not self.is_used and not self.is_expired and self.attempts < self.max_attempts
    
    def verify(self, code):
        """Verify OTP code"""
        self.attempts += 1
        self.save()
        
        if not self.is_valid:
            return False
        
        if self.code == code:
            self.is_used = True
            self.save()
            return True
        
        return False

# Utility functions
def get_user_by_phone(phone_number):
    """Get user by phone number"""
    return User.query.filter_by(phone_number=phone_number).first()

def create_user(phone_number, full_name=None, email=None):
    """Create new user"""
    user = User(
        phone_number=phone_number,
        full_name=full_name,
        email=email
    )
    return user.save()

def get_user_transactions(user_id, limit=10):
    """Get user transactions"""
    return Transaction.query.filter_by(user_id=user_id).order_by(
        Transaction.created_at.desc()
    ).limit(limit).all()

def create_transaction(user_id, transaction_type, amount, **kwargs):
    """Create new transaction"""
    transaction = Transaction(
        user_id=user_id,
        transaction_type=transaction_type,
        amount=amount,
        **kwargs
    )
    return transaction.save()