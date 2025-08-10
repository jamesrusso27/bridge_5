from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
import json

def connect_to(chain):
    if chain == 'source':
        api_url = "https://api.avax-test.network/ext/bc/C/rpc"
    if chain == 'destination':
        api_url = "https://data-seed-prebsc-1-s1.binance.org:8545/"
    if chain in ['source','destination']:
        w3 = Web3(Web3.HTTPProvider(api_url))
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        return w3

def get_contract_info(chain, contract_info):
    try:
        with open(contract_info, 'r') as f:
            contracts = json.load(f)
    except Exception as e:
        print("Failed to read contract info")
        return 0
    return contracts[chain]

def _checksum(addr):
    return Web3.to_checksum_address(addr)

def _send_tx(w3, fn, pk, chain_id):
    sender = w3.eth.account.from_key(pk).address
    gas = fn.estimate_gas({'from': sender})
    tx = fn.build_transaction({
        'from': sender,
        'nonce': w3.eth.get_transaction_count(sender),
        'gas': gas + 20000,
        'gasPrice': w3.eth.gas_price,
        'chainId': chain_id
    })
    signed = w3.eth.account.sign_transaction(tx, pk)
    return w3.eth.send_raw_transaction(signed.rawTransaction).hex()

def scan_blocks(chain, contract_info="contract_info.json"):
    if chain not in ['source','destination']:
        print(f"Invalid chain: {chain}")
        return 0
    with open(contract_info, 'r') as f:
        conf = json.load(f)
    warden_pk = conf.get("warden_private_key")
    src_meta = conf["source"]
    dst_meta = conf["destination"]
    w3_src = connect_to('source')
    w3_dst = connect_to('destination')
    src_addr = _checksum(src_meta["address"])
    dst_addr = _checksum(dst_meta["address"])
    src = w3_src.eth.contract(address=src_addr, abi=src_meta["abi"])
    dst = w3_dst.eth.contract(address=dst_addr, abi=dst_meta["abi"])
    if chain == 'source':
        latest = w3_src.eth.get_block_number()
        from_blk = max(0, latest - 5)
        try:
            events = src.events.Deposit.create_filter(from_block=from_blk, to_block=latest).get_all_entries()
        except:
            events = []
        for e in events:
            token = _checksum(e['args']['token'])
            recipient = _checksum(e['args']['recipient'])
            amount = int(e['args']['amount'])
            try:
                fn = dst.functions.wrap(token, recipient, amount)
                txh = _send_tx(w3_dst, fn, warden_pk, 97)
                print(txh)
            except Exception as ex:
                print(str(ex))
    if chain == 'destination':
        latest = w3_dst.eth.get_block_number()
        from_blk = max(0, latest - 5)
        try:
            events = dst.events.Unwrap.create_filter(from_block=from_blk, to_block=latest).get_all_entries()
        except:
            events = []
        for e in events:
            token = _checksum(e['args']['underlying_token'])
            recipient = _checksum(e['args']['to'])
            amount = int(e['args']['amount'])
            try:
                fn = src.functions.withdraw(token, recipient, amount)
                txh = _send_tx(w3_src, fn, warden_pk, 43113)
                print(txh)
            except Exception as ex:
                print(str(ex))
    return 1
