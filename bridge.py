from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
import json

RPC_SOURCE = "https://api.avax-test.network/ext/bc/C/rpc"
RPC_DEST   = "https://data-seed-prebsc-1-s1.binance.org:8545/"

def _w3(url):
    w3 = Web3(Web3.HTTPProvider(url))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3

def _cs(a): return Web3.to_checksum_address(a)

def _send(w3, fn, pk, chain_id):
    acct = w3.eth.account.from_key(pk)
    tx = fn.build_transaction({
        "from": acct.address,
        "nonce": w3.eth.get_transaction_count(acct.address),
        "gas": fn.estimate_gas({"from": acct.address}) + 20000,
        "gasPrice": w3.eth.gas_price,
        "chainId": chain_id
    })
    sig = w3.eth.account.sign_transaction(tx, pk)
    return w3.eth.send_raw_transaction(sig.rawTransaction).hex()

def scan_blocks(chain, contract_info="contract_info.json"):
    with open(contract_info) as f:
        cfg = json.load(f)

    pk = cfg["warden_private_key"]
    w3s = _w3(RPC_SOURCE)
    w3d = _w3(RPC_DEST)

    src = w3s.eth.contract(address=_cs(cfg["source"]["address"]), abi=cfg["source"]["abi"])
    dst = w3d.eth.contract(address=_cs(cfg["destination"]["address"]), abi=cfg["destination"]["abi"])

    if chain == "source":
        latest = w3s.eth.get_block_number()
        events = src.events.Deposit.create_filter(from_block=max(0, latest-5), to_block=latest).get_all_entries()
        for e in events:
            token = _cs(e["args"]["token"])
            to    = _cs(e["args"]["recipient"])
            amt   = int(e["args"]["amount"])
            _send(w3d, dst.functions.wrap(token, to, amt), pk, 97)
        return 1

    if chain == "destination":
        latest = w3d.eth.get_block_number()
        events = dst.events.Unwrap.create_filter(from_block=max(0, latest-5), to_block=latest).get_all_entries()
        for e in events:
            token = _cs(e["args"]["underlying_token"])
            to    = _cs(e["args"]["to"])
            amt   = int(e["args"]["amount"])
            _send(w3s, src.functions.withdraw(token, to, amt), pk, 43113)
        return 1

    print("Invalid chain")
    return 0
