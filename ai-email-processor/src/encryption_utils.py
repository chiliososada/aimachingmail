# NOTE: This decryption logic assumes that the passwords stored in the 
# 'email_smtp_settings.smtp_password_encrypted' field were encrypted 
# using the 'encrypt' function in this module with the same ENCRYPTION_KEY.
# If passwords are not already encrypted in this way, IMAP login will fail,
# and a separate migration script will be needed to encrypt existing passwords.

import base64
import hashlib
from cryptography.fernet import Fernet, InvalidToken
from src.config import Config

class EncryptionError(Exception):
    """Custom exception for encryption errors."""
    pass

class DecryptionError(Exception):
    """Custom exception for decryption errors."""
    pass

def _derive_key(key: str) -> bytes:
    """Derives a Fernet-compatible key from the input string key."""
    return base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest())

def encrypt(text: str, key: str) -> bytes:
    """Encrypts text using Fernet symmetric encryption."""
    try:
        fernet_key = _derive_key(key)
        f = Fernet(fernet_key)
        encrypted_text = f.encrypt(text.encode())
        return encrypted_text
    except Exception as e:
        # Log error or handle appropriately
        print(f"Encryption failed: {e}")
        raise EncryptionError(f"Encryption failed: {e}") from e

def decrypt(encrypted_text: bytes, key: str) -> str | None:
    """Decrypts text using Fernet symmetric encryption."""
    try:
        fernet_key = _derive_key(key)
        f = Fernet(fernet_key)
        decrypted_text = f.decrypt(encrypted_text)
        return decrypted_text.decode()
    except InvalidToken:
        print("Decryption failed: Invalid token or incorrect key.")
        # It's important to not reveal too much about why decryption failed for security.
        # For example, don't differentiate between "wrong key" and "corrupted data".
        raise DecryptionError("Decryption failed: Invalid token or incorrect key.")
    except Exception as e:
        print(f"Decryption failed: {e}")
        raise DecryptionError(f"Decryption failed: {e}") from e

if __name__ == '__main__':
    # Example Usage (optional - for testing)
    # Ensure ENCRYPTION_KEY is set in your .env file or environment for this test to work
    # from dotenv import load_dotenv
    # import os
    # load_dotenv() # Load environment variables from .env file
    # test_key = os.getenv("ENCRYPTION_KEY")

    # For testing without relying on .env, you can use a placeholder key,
    # but remember that Config.ENCRYPTION_KEY will be used in the actual application.
    test_key = "your-super-secret-and-long-enough-passphrase-for-testing"
    
    if not test_key:
        print("Please set the ENCRYPTION_KEY environment variable for testing.")
    else:
        original_text = "This is a secret message!"
        print(f"Original: {original_text}")

        try:
            encrypted = encrypt(original_text, test_key)
            print(f"Encrypted: {encrypted}")

            decrypted = decrypt(encrypted, test_key)
            print(f"Decrypted: {decrypted}")

            if decrypted == original_text:
                print("Encryption and decryption test successful!")
            else:
                print("Decryption did not match original text.")

        except EncryptionError as e:
            print(f"Test Encryption Error: {e}")
        except DecryptionError as e:
            print(f"Test Decryption Error: {e}")

        # Test with a wrong key
        wrong_key = "this-is-a-wrong-key-for-sure123"
        print("\nTesting decryption with a wrong key...")
        try:
            if encrypted:
                decrypted_with_wrong_key = decrypt(encrypted, wrong_key)
                print(f"Decrypted with wrong key: {decrypted_with_wrong_key}") # Should be None or raise error
        except DecryptionError as e:
            print(f"Caught expected error with wrong key: {e}")
        
        # Test with invalid encrypted text
        print("\nTesting decryption with invalid encrypted text...")
        invalid_encrypted_text = b"invalid_encrypted_text"
        try:
            decrypted_invalid_text = decrypt(invalid_encrypted_text, test_key)
            print(f"Decrypted invalid text: {decrypted_invalid_text}") # Should be None or raise error
        except DecryptionError as e:
            print(f"Caught expected error with invalid text: {e}")
