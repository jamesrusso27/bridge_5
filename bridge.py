from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
import os, json

FUJI_RPC = "https://api.avax-test.network/ext/bc/C/rpc"
BSC_RPC  = "https://data-seed-prebsc-1-s1.binance.org:8545/"
FUJI_CHAIN_ID = 43113
BSC_CHAIN_ID  = 97

def _w3(which):
    url = FUJI_RPC if which == "source" else BSC_RPC
    w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 30}))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3

def _key():
    k = os.environ.get("WARDEN_KEY", "").strip()
    if not k and os.path.exists("secret_key.txt"):
        with open("secret_key.txt") as f:
            k = f.read().strip()
    if not k and os.path.exists("sk.txt"):
        with open("sk.txt") as f:
            k = f.read().strip()
    if not k:
        raise RuntimeError("missing private key (set WARDEN_KEY or create secret_key.txt)")
    return k

def _contracts():
    with open("contract_info.json") as f:
        info = json.load(f)
    s_addr = Web3.to_checksum_address(info["source"]["address"])
    d_addr = Web3.to_checksum_address(info["destination"]["address"])
    s = _w3("source").eth.contract(address=s_addr, abi=info["source"]["abi"])
    d = _w3("destination").eth.contract(address=d_addr, abi=info["destination"]["abi"])
    return s, d

def _send_tx(w3, fn, chain_id, sender, key):
    tx = fn.build_transaction({
        "from": sender,
        "nonce": w3.eth.get_transaction_count(sender),
        "gasPrice": w3.eth.gas_price,
        "chainId": chain_id,
    })
    try:
        tx["gas"] = w3.eth.estimate_gas(tx)
    except Exception:
        tx["gas"] = 600000
    signed = w3.eth.account.sign_transaction(tx, key)
    return w3.eth.send_raw_transaction(signed.rawTransaction)

def scan_blocks(which, contract_info="contract_info.json"):
    if which not in ["source", "destination"]:
        return
    key = _key()
    s, d = _contracts()
    w_src = _w3("source")
    w_dst = _w3("destination")
    acct_src = w_src.eth.account.from_key(key).address
    acct_dst = w_dst.eth.account.from_key(key).address
    start_src = max(0, w_src.eth.block_number - 5)
    start_dst = max(0, w_dst.eth.block_number - 5)

    try:
        deposits = s.events.Deposit.create_filter(fromBlock=start_src, toBlock="latest").get_all_entries()
    except Exception:
        deposits = []
    for ev in deposits:
        t = Web3.to_checksum_address(ev["args"]["token"])
        r = Web3.to_checksum_address(ev["args"]["recipient"])
        a = int(ev["args"]["amount"])
        _send_tx(w_dst, d.functions.wrap(t, r, a), BSC_CHAIN_ID, acct_dst, key)

    try:
        unwraps = d.events.Unwrap.create_filter(fromBlock=start_dst, toBlock="latest").get_all_entries()
    except Exception:
        unwraps = []
    for ev in unwraps:
        t = Web3.to_checksum_address(ev["args"]["underlying_token"])
        r = Web3.to_checksum_address(ev["args"]["to"])
        a = int(ev["args"]["amount"])
        _send_tx(w_src, s.functions.withdraw(t, r, a), FUJI_CHAIN_ID, acct_src, key)

if __name__ == "__main__":
    scan_blocks("source")
    scan_blocks("destination")
