from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
import os, json, sys

FUJI_RPC="https://api.avax-test.network/ext/bc/C/rpc"
BSC_RPC="https://data-seed-prebsc-1-s1.binance.org:8545/"
FUJI_CHAIN_ID=43113
BSC_CHAIN_ID=97

def _w3(name):
    url=FUJI_RPC if name=="source" else BSC_RPC
    w3=Web3(Web3.HTTPProvider(url))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3

def _key():
    k=os.environ.get("WARDEN_KEY")
    if not k and os.path.exists("secret_key.txt"): k=open("secret_key.txt").read().strip()
    if not k and os.path.exists("sk.txt"): k=open("sk.txt").read().strip()
    if not k: raise RuntimeError("missing private key")
    return k

def _contracts():
    with open("contract_info.json") as f:
        j=json.load(f)
    s=_w3("source").eth.contract(address=Web3.to_checksum_address(j["source"]["address"]), abi=j["source"]["abi"])
    d=_w3("destination").eth.contract(address=Web3.to_checksum_address(j["destination"]["address"]), abi=j["destination"]["abi"])
    return s,d

def _send_tx(w3, fn, chain_id, sender, key):
    tx=fn.build_transaction({
        "from": sender,
        "nonce": w3.eth.get_transaction_count(sender),
        "gasPrice": w3.eth.gas_price,
        "chainId": chain_id
    })
    try:
        gas=w3.eth.estimate_gas(tx)
        tx["gas"]=gas
    except:
        tx["gas"]=600000
    signed=w3.eth.account.sign_transaction(tx, key)
    return w3.eth.send_raw_transaction(signed.rawTransaction)

def scan_blocks(chain, contract_info="contract_info.json"):
    if chain not in ["source","destination"]: return
    k=_key()
    s,d=_contracts()
    w_src=_w3("source")
    w_dst=_w3("destination")
    acct_src=w_src.eth.account.from_key(k).address
    acct_dst=w_dst.eth.account.from_key(k).address
    latest_src=w_src.eth.block_number
    latest_dst=w_dst.eth.block_number
    from_src=max(0, latest_src-5)
    from_dst=max(0, latest_dst-5)
    try:
        dep=s.events.Deposit.create_filter(fromBlock=from_src, toBlock="latest").get_all_entries()
    except:
        dep=[]
    for e in dep:
        t=Web3.to_checksum_address(e["args"]["token"])
        r=Web3.to_checksum_address(e["args"]["recipient"])
        a=int(e["args"]["amount"])
        _send_tx(w_dst, d.functions.wrap(t, r, a), BSC_CHAIN_ID, acct_dst, k)
    try:
        un=d.events.Unwrap.create_filter(fromBlock=from_dst, toBlock="latest").get_all_entries()
    except:
        un=[]
    for e in un:
        t=Web3.to_checksum_address(e["args"]["underlying_token"])
        r=Web3.to_checksum_address(e["args"]["to"])
        a=int(e["args"]["amount"])
        _send_tx(w_src, s.functions.withdraw(t, r, a), FUJI_CHAIN_ID, acct_src, k)

if __name__=="__main__":
    scan_blocks("source")
    scan_blocks("destination")
