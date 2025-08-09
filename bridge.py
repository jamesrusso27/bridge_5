from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

FUJI_RPC="https://api.avax-test.network/ext/bc/C/rpc"
BSC_RPC="https://data-seed-prebsc-1-s1.binance.org:8545/"
FUJI_CHAIN_ID=43113
BSC_CHAIN_ID=97

def _w3(url):
    w3=Web3(Web3.HTTPProvider(url))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3

def _load():
    import json
    with open("contract_info.json") as f:
        j=json.load(f)
    warden_key=j["warden"]["private_key"]
    src_addr=Web3.to_checksum_address(j["source"]["address"])
    dst_addr=Web3.to_checksum_address(j["destination"]["address"])
    w_src=_w3(FUJI_RPC)
    w_dst=_w3(BSC_RPC)
    src=w_src.eth.contract(address=src_addr, abi=j["source"]["abi"])
    dst=w_dst.eth.contract(address=dst_addr, abi=j["destination"]["abi"])
    acct_src=w_src.eth.account.from_key(warden_key).address
    acct_dst=w_dst.eth.account.from_key(warden_key).address
    return w_src,w_dst,src,dst,warden_key,acct_src,acct_dst

def _send_tx(w3, fn, chain_id, sender, key):
    tx=fn.build_transaction({
        "from": sender,
        "nonce": w3.eth.get_transaction_count(sender),
        "gasPrice": w3.eth.gas_price,
        "chainId": chain_id
    })
    try:
        tx["gas"]=w3.eth.estimate_gas(tx)
    except:
        tx["gas"]=600000
    signed=w3.eth.account.sign_transaction(tx, key)
    return w3.eth.send_raw_transaction(signed.rawTransaction)

def scan():
    w_src,w_dst,src,dst,key,acct_src,acct_dst=_load()
    latest_src=w_src.eth.block_number
    latest_dst=w_dst.eth.block_number
    from_src=max(0, latest_src-250)
    from_dst=max(0, latest_dst-250)
    try:
        dep=src.events.Deposit.create_filter(fromBlock=from_src, toBlock="latest").get_all_entries()
    except:
        dep=[]
    for e in dep:
        t=Web3.to_checksum_address(e["args"]["token"])
        r=Web3.to_checksum_address(e["args"]["recipient"])
        a=int(e["args"]["amount"])
        _send_tx(w_dst, dst.functions.wrap(t, r, a), BSC_CHAIN_ID, acct_dst, key)
    try:
        un=dst.events.Unwrap.create_filter(fromBlock=from_dst, toBlock="latest").get_all_entries()
    except:
        un=[]
    for e in un:
        t=Web3.to_checksum_address(e["args"]["underlying_token"])
        r=Web3.to_checksum_address(e["args"]["to"])
        a=int(e["args"]["amount"])
        _send_tx(w_src, src.functions.withdraw(t, r, a), FUJI_CHAIN_ID, acct_src, key)

if __name__=="__main__":
    scan()
