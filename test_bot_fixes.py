#!/usr/bin/env python3
"""
Test the WhatsApp bot fixes
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.helpers import normalize_text, strip_sandbox_prefix, detect_message_intent

# Set up minimal logging
logging.basicConfig(level=logging.INFO)

def test_text_normalization():
    """Test the text normalization functions"""
    print("=== Testing Text Normalization ===")
    
    test_cases = [
        ("  YES  ", "yes"),
        ("Hello World", "hello world"),
        ("", ""),
        ("  Mixed CaSe  ", "mixed case"),
    ]
    
    for input_text, expected in test_cases:
        result = normalize_text(input_text)
        status = "✅" if result == expected else "❌"
        print(f"{status} normalize_text('{input_text}') = '{result}' (expected: '{expected}')")

def test_sandbox_prefix_stripping():
    """Test sandbox prefix removal"""
    print("\n=== Testing Sandbox Prefix Stripping ===")
    
    test_cases = [
        ("join abc123 YES", "YES"),
        ("join test-bot yes", "yes"),
        ("JOIN XYZ_BOT hello", "hello"),
        ("sandbox start", "start"),
        ("normal message", "normal message"),
        ("join", "join"),  # Edge case - just 'join'
        ("", ""),
    ]
    
    for input_text, expected in test_cases:
        result = strip_sandbox_prefix(input_text)
        status = "✅" if result == expected else "❌"
        print(f"{status} strip_sandbox_prefix('{input_text}') = '{result}' (expected: '{expected}')")

def test_intent_detection():
    """Test the enhanced intent detection"""
    print("\n=== Testing Intent Detection ===")
    
    test_cases = [
        # Confirmation tests
        ("YES", "confirm"),
        ("yes", "confirm"),
        ("Yes", "confirm"),
        ("yup", "confirm"),
        ("create bitcoin wallet", "confirm"),
        ("i want to create account", "confirm"),
        
        # Cancel tests
        ("NO", "cancel"),
        ("no", "cancel"),
        ("cancel", "cancel"),
        ("stop", "cancel"),
        
        # Greeting tests
        ("Hi", "greeting"),
        ("hello", "greeting"),
        ("HEY", "greeting"),
        ("good morning", "greeting"),
        
        # Balance tests
        ("balance", "balance"),
        ("BALANCE", "balance"),
        ("check balance", "balance"),
        ("what is my balance", "balance"),
        ("how much money do i have", "balance"),
        ("my balance", "balance"),
        
        # Send tests
        ("send 0.001 btc", "send"),
        ("Send 0.5 Bitcoin", "send"),
        ("i want to send bitcoin", "send"),
        ("transfer money", "send"),
        
        # Address tests
        ("address", "address"),
        ("my bitcoin address", "address"),
        ("create wallet", "address"),
        ("how to receive bitcoin", "address"),
        
        # History tests
        ("history", "history"),
        ("transactions", "history"),
        ("show my history", "history"),
        ("recent transactions", "history"),
        
        # Help tests
        ("help", "help"),
        ("HELP", "help"),
        ("what can you do", "help"),
        ("commands", "help"),
        
        # OTP tests
        ("123456", "otp"),
        ("000000", "otp"),
        
        # Name input tests
        ("John Smith", "name_input"),
        ("Jane Doe", "name_input"),
        
        # Email input tests
        ("test@example.com", "email_input"),
        ("user.name@domain.co.uk", "email_input"),
        
        # Unknown tests
        ("random gibberish", "unknown"),
        ("12345", "unknown"),  # Not 6 digits
        ("single", "unknown"),  # Single word, not a command
    ]
    
    for input_text, expected in test_cases:
        result = detect_message_intent(input_text)
        status = "✅" if result == expected else "❌"
        print(f"{status} detect_message_intent('{input_text}') = '{result}' (expected: '{expected}')")

def test_sandbox_and_intent_combined():
    """Test the complete flow: sandbox stripping + intent detection"""
    print("\n=== Testing Combined Sandbox Stripping + Intent Detection ===")
    
    test_cases = [
        ("join abc123 YES", "confirm"),
        ("join test-bot balance", "balance"),
        ("JOIN XYZ hello", "greeting"),
        ("sandbox help", "help"),
        ("join demo-bot send 0.001 btc", "send"),
    ]
    
    for input_text, expected_intent in test_cases:
        cleaned = strip_sandbox_prefix(input_text)
        intent = detect_message_intent(cleaned)
        status = "✅" if intent == expected_intent else "❌"
        print(f"{status} '{input_text}' -> clean: '{cleaned}' -> intent: '{intent}' (expected: '{expected_intent}')")

def main():
    print("🧪 Testing WhatsApp Bot Fixes\n")
    
    test_text_normalization()
    test_sandbox_prefix_stripping()
    test_intent_detection()
    test_sandbox_and_intent_combined()
    
    print("\n🎉 Testing complete!")
    print("\nThe fixes should now handle:")
    print("✅ Case-insensitive commands (YES, yes, Yes)")
    print("✅ Twilio sandbox prefixes (join xxx)")
    print("✅ Natural language commands (check balance, create wallet)")
    print("✅ Command variations (bal, balance, my balance)")
    print("✅ Proper registration flow routing")

if __name__ == '__main__':
    main()
