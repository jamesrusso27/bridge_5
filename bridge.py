from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
import json
import time

RPC_SOURCE = "https://api.avax-test.network/ext/bc/C/rpc"
RPC_DEST   = "https://data-seed-prebsc-1-s1.binance.org:8545/"

CHAINID_FUJI = 43113
CHAINID_BSCT = 97

LOOKBACK_BLOCKS = 2000

def _w3(url):
    w3 = Web3(Web3.HTTPProvider(url))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3

def _cs(a):
    return Web3.to_checksum_address(a)

def _send_and_wait(w3, fn, pk, chain_id, max_retries=3):
    acct = w3.eth.account.from_key(pk)
    base_gp = w3.eth.gas_price or 1_000_000_000
    for attempt in range(max_retries):
        try:
            nonce = w3.eth.get_transaction_count(acct.address, "pending")
            gas_est = fn.estimate_gas({"from": acct.address})
            tx = fn.build_transaction({
                "from": acct.address,
                "nonce": nonce,
                "gas": gas_est + 20000,
                "gasPrice": int(base_gp * (1 + 0.15 * attempt)),
                "chainId": chain_id
            })
            sig = w3.eth.account.sign_transaction(tx, pk)
            tx_hash = w3.eth.send_raw_transaction(sig.raw_transaction)
            w3.eth.wait_for_transaction_receipt(tx_hash)
            return tx_hash.hex()
        except ValueError as e:
            msg = str(e)
            if ("replacement transaction underpriced" in msg) or ("nonce too low" in msg):
                time.sleep(0.5)
                continue
            raise
    raise RuntimeError("Failed to send tx after retries")

def scan_blocks(chain, contract_info="contract_info.json"):
    with open(contract_info) as f:
        cfg = json.load(f)

    pk = cfg["warden_private_key"]
    w3s = _w3(RPC_SOURCE)
    w3d = _w3(RPC_DEST)

    src = w3s.eth.contract(address=_cs(cfg["source"]["address"]),      abi=cfg["source"]["abi"])
    dst = w3d.eth.contract(address=_cs(cfg["destination"]["address"]), abi=cfg["destination"]["abi"])

    if chain == "source":
        latest = w3s.eth.block_number
        events = src.events.Deposit.create_filter(
            from_block=max(0, latest - LOOKBACK_BLOCKS),
            to_block=latest
        ).get_all_entries()
        for e in events:
            token = _cs(e["args"]["token"])
            to    = _cs(e["args"]["recipient"])
            amt   = int(e["args"]["amount"])
            _send_and_wait(w3d, dst.functions.wrap(token, to, amt), pk, CHAINID_BSCT)
        return 1

    if chain == "destination":
        latest = w3d.eth.block_number
        events = dst.events.Unwrap.create_filter(
            from_block=max(0, latest - LOOKBACK_BLOCKS),
            to_block=latest
        ).get_all_entries()
        for e in events:
            token = _cs(e["args"]["underlying_token"])
            to    = _cs(e["args"]["to"])
            amt   = int(e["args"]["amount"])
            _send_and_wait(w3s, src.functions.withdraw(token, to, amt), pk, CHAINID_FUJI)
        return 1

    return 0
