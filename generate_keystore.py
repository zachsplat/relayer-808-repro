"""Create config/keys/anvil0.json: an encrypted keystore for anvil's well-known dev account #0.
The key is public test material (anvil prints it at startup); never use it anywhere real.
pip install eth-account, then: python3 generate_keystore.py
"""
import json, os
from eth_account import Account
KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
os.makedirs("config/keys", exist_ok=True)
json.dump(Account.encrypt(KEY, "Repro808Pass!"), open("config/keys/anvil0.json", "w"))
print("wrote config/keys/anvil0.json for", Account.from_key(KEY).address)
