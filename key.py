"""Utility script to generate a Fernet encryption key.

Run directly (python key.py) to print a fresh key you can paste into your .env as FERNET_KEY.
This file should NOT be imported by the app; it performs generation only under __main__.
"""
from cryptography.fernet import Fernet


def generate_fernet_key() -> str:
	return Fernet.generate_key().decode()


if __name__ == "__main__":
	print(generate_fernet_key())