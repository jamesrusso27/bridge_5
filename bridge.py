
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from web3.exceptions import ContractLogicError
from eth_account import Account
import json, os
from datetime import datetime

def connect_to(x: str) -> Web3:
    u = "https://api.avax-test.network/ext/bc/C/rpc" if x == "source" else "https://data-seed-prebsc-1-s1.binance.org:8545/"
    w3 = Web3(Web3.HTTPProvider(u, request_kwargs={"timeout": 30}))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    if not w3.is_connected(): raise RuntimeError("rpc")
    return w3

def get_info(k: str, p: str):
    with open(p, "r") as f: d = json.load(f)
    if k not in d: raise KeyError(k)
    return d[k]

def load_c(w3: Web3, info: dict):
    return w3.eth.contract(address=Web3.to_checksum_address(info["address"]), abi=info["abi"])

def load_key() -> str:
    e = os.getenv("WARDEN_KEY")
    if e: return e if e.startswith("0x") else "0x"+e.strip()
    for n in ["secret_key.txt","sk.txt","warden_key.txt"]:
        if os.path.exists(n):
            r = open(n).read().strip()
            return r if r.startswith("0x") else "0x"+r
    if os.path.exists("secrets.json"):
        try:
            s = json.loads(open("secrets.json").read()).get("WARDEN_KEY")
            if s: return s if s.startswith("0x") else "0x"+s
        except Exception: pass
    raise RuntimeError("key")

def acct(w3: Web3, k: str):
    a = Account.from_key(k)
    w3.eth.default_account = a.address
    return a

def fees(w3: Web3, tx: dict):
    try: b = w3.eth.get_block("latest").get("baseFeePerGas")
    except Exception: b = None
    if b is not None:
        tx["maxPriorityFeePerGas"] = w3.to_wei(1,"gwei")
        tx["maxFeePerGas"] = int(b*2)+tx["maxPriorityFeePerGas"]
    else:
        tx["gasPrice"] = w3.eth.gas_price
    return tx

def send(w3: Web3, a, fn) -> str:
    tx = {"from": a.address, "nonce": w3.eth.get_transaction_count(a.address), "value": 0, "chainId": w3.eth.chain_id}
    tx = fees(w3, tx)
    try: tx["gas"] = int(fn.estimate_gas(tx)*1.25)
    except Exception: tx["gas"] = 600000
    b = fn.build_transaction(tx)
    s = w3.eth.account.sign_transaction(b, private_key=a.key)
    h = w3.eth.send_raw_transaction(s.rawTransaction)
    r = w3.eth.wait_for_transaction_receipt(h, timeout=120)
    if r.status != 1: raise RuntimeError("tx")
    return h.hex()

def scan_blocks(side: str, path: str = "contract_info.json") -> int:
    if side not in ["source","destination"]: return 0
    l_w3 = connect_to(side)
    c_w3 = connect_to("destination" if side=="source" else "source")
    s = get_info("source", path); d = get_info("destination", path)
    l_info = s if side=="source" else d
    c_info = d if side=="source" else s
    L = load_c(l_w3, l_info); C = load_c(c_w3, c_info)
    a = acct(c_w3, load_key())
    latest = l_w3.eth.block_number; frm = max(0, latest-5)
    print(f"[{datetime.utcnow().isoformat()}Z] scan {side} {frm}..{latest}")
    n = 0
    if side=="source":
        try:
            flt = L.events.Deposit.createFilter(fromBlock=frm, toBlock=latest)
            logs = flt.get_all_entries()
        except Exception:
            logs = L.events.Deposit().get_logs(from_block=frm, to_block=latest)
        for ev in logs:
            args = ev["args"]
            t, r, m = args["token"], args["recipient"], int(args["amount"])
            try:
                h = send(c_w3, a, C.functions.wrap(t, r, m))
                print(h); n += 1
            except ContractLogicError as e:
                print(f"revert wrap {e}")
            except Exception as e:
                print(f"fail wrap {e}")
    else:
        try:
            flt = L.events.Unwrap.createFilter(fromBlock=frm, toBlock=latest)
            logs = flt.get_all_entries()
        except Exception:
            logs = L.events.Unwrap().get_logs(from_block=frm, to_block=latest)
        for ev in logs:
            args = ev["args"]
            u, to, m = args["underlying_token"], args["to"], int(args["amount"])
            try:
                h = send(c_w3, a, C.functions.withdraw(u, to, m))
                print(h); n += 1
            except ContractLogicError as e:
                print(f"revert withdraw {e}")
            except Exception as e:
                print(f"fail withdraw {e}")
    if n==0: print("noops")
    return n

if __name__ == "__main__":
    import sys
    s = sys.argv[1] if len(sys.argv)>1 else "source"
    scan_blocks(s, "contract_info.json")
