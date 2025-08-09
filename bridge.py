from web3 import Web3
from web3.providers.rpc import HTTPProvider
from web3.middleware import ExtraDataToPOAMiddleware
from datetime import datetime
import json
import pandas as pd


def connect_to(chain):
    if chain == 'source':
        api_url = f"https://api.avax-test.network/ext/bc/C/rpc"

    if chain == 'destination':
        api_url = f"https://data-seed-prebsc-1-s1.binance.org:8545/"

    if chain in ['source','destination']:
        w3 = Web3(Web3.HTTPProvider(api_url))
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3


def get_contract_info(chain, contract_info):
    try:
        with open(contract_info, 'r')  as f:
            contracts = json.load(f)
    except Exception as e:
        print( f"Failed to read contract info\nPlease contact your instructor\n{e}" )
        return 0
    return contracts[chain]


def scan_blocks(chain, contract_info="contract_info.json"):
    if chain not in ['source','destination']:
        print( f"Invalid chain: {chain}" )
        return 0
    
    w3 = connect_to(chain)
    latest_block = w3.eth.block_number
    start_block = latest_block - 5
    
    info = get_contract_info(chain, contract_info)
    contract_address = info['address']
    contract_abi = info['abi']
    
    contract = w3.eth.contract(address=Web3.to_checksum_address(contract_address), abi=contract_abi)
    
    warden_key = "e4e13c4c7e72dcd21d03cb35768064c63c8a41d6d98ab4127b4dadbad0190d84"
    warden_address = "0x24AeA5a1D28f983c2E9709640265047dF512Ac8"
    
    if chain == 'source':
        event_filter = contract.events.Deposit.create_filter(fromBlock=start_block, toBlock='latest')
        events = event_filter.get_all_entries()
        
        if events:
            dest_w3 = connect_to('destination')
            dest_info = get_contract_info('destination', contract_info)
            dest_contract = dest_w3.eth.contract(
                address=Web3.to_checksum_address(dest_info['address']), 
                abi=dest_info['abi']
            )
            
            for event in events:
                token = event['args']['token']
                recipient = event['args']['recipient']
                amount = event['args']['amount']
                
                nonce = dest_w3.eth.get_transaction_count(warden_address)
                
                txn = dest_contract.functions.wrap(
                    token,
                    recipient,
                    amount
                ).build_transaction({
                    'chainId': 97,
                    'gas': 300000,
                    'gasPrice': dest_w3.to_wei('10', 'gwei'),
                    'nonce': nonce,
                })
                
                signed_txn = dest_w3.eth.account.sign_transaction(txn, warden_key)
                tx_hash = dest_w3.eth.send_raw_transaction(signed_txn.rawTransaction)
                dest_w3.eth.wait_for_transaction_receipt(tx_hash)
    
    elif chain == 'destination':
        event_filter = contract.events.Unwrap.create_filter(fromBlock=start_block, toBlock='latest')
        events = event_filter.get_all_entries()
        
        if events:
            source_w3 = connect_to('source')
            source_info = get_contract_info('source', contract_info)
            source_contract = source_w3.eth.contract(
                address=Web3.to_checksum_address(source_info['address']), 
                abi=source_info['abi']
            )
            
            for event in events:
                underlying_token = event['args']['underlying_token']
                recipient = event['args']['to']
                amount = event['args']['amount']
                
                nonce = source_w3.eth.get_transaction_count(warden_address)
                
                txn = source_contract.functions.withdraw(
                    underlying_token,
                    recipient,
                    amount
                ).build_transaction({
                    'chainId': 43113,
                    'gas': 300000,
                    'gasPrice': source_w3.to_wei('30', 'gwei'),
                    'nonce': nonce,
                })
                
                signed_txn = source_w3.eth.account.sign_transaction(txn, warden_key)
                tx_hash = source_w3.eth.send_raw_transaction(signed_txn.rawTransaction)
                source_w3.eth.wait_for_transaction_receipt(tx_hash)