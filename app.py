from flask import Flask, render_template, request, jsonify
from algosdk import account, mnemonic
from algosdk.v2client import algod
from algosdk.transaction import AssetConfigTxn, AssetTransferTxn, PaymentTxn, AssetOptInTxn, calculate_group_id
import time

app = Flask(__name__)


# Initialize Algod client
def create_algod_client():
    algod_address = "https://testnet-api.algonode.cloud"
    algod_token = ""
    return algod.AlgodClient(algod_token, algod_address)


# Create a new account
def create_account():
    private_key, address = account.generate_account()
    return private_key, address


# Wait for transaction confirmation
def wait_for_confirmation(client, txid):
    last_round = client.status().get('last-round')
    txinfo = client.pending_transaction_info(txid)
    while not (txinfo.get('confirmed-round') and txinfo.get('confirmed-round') > 0):
        print("Waiting for confirmation...")
        last_round += 1
        client.status_after_block(last_round)
        txinfo = client.pending_transaction_info(txid)
    print(f"Transaction {txid} confirmed in round {txinfo.get('confirmed-round')}.")
    return txinfo


# Create ASA (UCTZAR)
def create_asa(client, creator, creator_private_key, total):
    params = client.suggested_params()
    txn = AssetConfigTxn(
        sender=creator,
        sp=params,
        total=total,
        default_frozen=False,
        unit_name="UCTZAR",
        asset_name="UCT South African Rand",
        manager=creator,
        reserve=creator,
        freeze=creator,
        clawback=creator,
        decimals=6
    )
    signed_txn = txn.sign(creator_private_key)
    tx_id = client.send_transaction(signed_txn)
    response = wait_for_confirmation(client, tx_id)
    return response['asset-index']


# Opt-in to ASA
def opt_in_asa(client, address, private_key, asset_id):
    params = client.suggested_params()
    txn = AssetOptInTxn(address, params, asset_id)
    signed_txn = txn.sign(private_key)
    tx_id = client.send_transaction(signed_txn)
    wait_for_confirmation(client, tx_id)


# Liquidity Pool
class LiquidityPool:
    def __init__(self, algo_amount, uctzar_amount):
        self.algo_amount = algo_amount
        self.uctzar_amount = uctzar_amount
        self.lp_tokens = (algo_amount * uctzar_amount) ** 0.5
        self.fees = 0

    def add_liquidity(self, algo_amount, uctzar_amount):
        ratio = min(algo_amount / self.algo_amount, uctzar_amount / self.uctzar_amount)
        minted_tokens = self.lp_tokens * ratio
        self.algo_amount += algo_amount
        self.uctzar_amount += uctzar_amount
        self.lp_tokens += minted_tokens
        return minted_tokens

    def remove_liquidity(self, lp_tokens):
        ratio = lp_tokens / self.lp_tokens
        algo_amount = self.algo_amount * ratio
        uctzar_amount = self.uctzar_amount * ratio
        self.algo_amount -= algo_amount
        self.uctzar_amount -= uctzar_amount
        self.lp_tokens -= lp_tokens
        return algo_amount, uctzar_amount

    def swap_algo_to_uctzar(self, algo_amount):
        fee = algo_amount * 0.003
        algo_amount_with_fee = algo_amount - fee
        uctzar_return = (self.uctzar_amount * algo_amount_with_fee) / (self.algo_amount + algo_amount_with_fee)
        self.algo_amount += algo_amount
        self.uctzar_amount -= uctzar_return
        self.fees += fee
        return uctzar_return

    def swap_uctzar_to_algo(self, uctzar_amount):
        fee = uctzar_amount * 0.003
        uctzar_amount_with_fee = uctzar_amount - fee
        algo_return = (self.algo_amount * uctzar_amount_with_fee) / (self.uctzar_amount + uctzar_amount_with_fee)
        self.uctzar_amount += uctzar_amount
        self.algo_amount -= algo_return
        self.fees += fee
        return algo_return


# Atomic transaction for adding liquidity
def add_liquidity_atomic(client, sender, sender_pk, pool_address, algo_amount, uctzar_amount, uctzar_id):
    params = client.suggested_params()

    # Create transactions
    algo_txn = PaymentTxn(sender, params, pool_address, algo_amount)
    uctzar_txn = AssetTransferTxn(sender, params, pool_address, uctzar_amount, uctzar_id)

    # Group transactions
    gid = calculate_group_id([algo_txn, uctzar_txn])
    algo_txn.group = gid
    uctzar_txn.group = gid

    # Sign transactions
    signed_algo_txn = algo_txn.sign(sender_pk)
    signed_uctzar_txn = uctzar_txn.sign(sender_pk)

    # Send grouped transactions
    tx_id = client.send_transactions([signed_algo_txn, signed_uctzar_txn])

    wait_for_confirmation(client, tx_id)

    return tx_id


# Atomic transaction for swapping
def swap_atomic(client, sender, sender_pk, pool_address, pool_pk, amount_in, asset_id_in, amount_out, asset_id_out):
    params = client.suggested_params()

    # Create transactions
    if asset_id_in == 0:  # ALGO
        txn_in = PaymentTxn(sender, params, pool_address, amount_in)
    else:
        txn_in = AssetTransferTxn(sender, params, pool_address, amount_in, asset_id_in)

    if asset_id_out == 0:  # ALGO
        txn_out = PaymentTxn(pool_address, params, sender, amount_out)
    else:
        txn_out = AssetTransferTxn(pool_address, params, sender, amount_out, asset_id_out)

    # Group transactions
    gid = calculate_group_id([txn_in, txn_out])
    txn_in.group = gid
    txn_out.group = gid

    # Sign transactions
    signed_txn_in = txn_in.sign(sender_pk)
    signed_txn_out = txn_out.sign(pool_pk)

    # Send grouped transactions
    tx_id = client.send_transactions([signed_txn_in, signed_txn_out])

    wait_for_confirmation(client, tx_id)

    return tx_id


# Global variables to store simulation state
client = create_algod_client()
creator_private_key, creator_address = create_account()
lp1_private_key, lp1_address = create_account()
lp2_private_key, lp2_address = create_account()
trader1_private_key, trader1_address = create_account()
trader2_private_key, trader2_address = create_account()
pool_private_key, pool_address = create_account()
uctzar_id = None
pool = None


@app.route('/')
def index():
    return render_template('index.html', creator_address=creator_address)


@app.route('/fund_creator', methods=['POST'])
def fund_creator():
    global uctzar_id, pool

    account_info = client.account_info(creator_address)
    creator_balance = account_info.get('amount')

    if creator_balance < 2000000:
        return jsonify({"error": "Insufficient funds in creator account. Please add more ALGOs and try again."})

    # Fund accounts
    params = client.suggested_params()
    funding_amount = 300000  # 0.3 ALGOs
    for address in [lp1_address, lp2_address, trader1_address, trader2_address, pool_address]:
        txn = PaymentTxn(creator_address, params, address, funding_amount)
        signed_txn = txn.sign(creator_private_key)
        client.send_transaction(signed_txn)
        wait_for_confirmation(client, signed_txn.get_txid())

    # Create UCTZAR ASA
    uctzar_id = create_asa(client, creator_address, creator_private_key, 1000000000)

    # Opt-in to UCTZAR
    for address, pk in [(lp1_address, lp1_private_key), (lp2_address, lp2_private_key),
                        (trader1_address, trader1_private_key), (trader2_address, trader2_private_key),
                        (pool_address, pool_private_key)]:
        opt_in_asa(client, address, pk, uctzar_id)

    # Transfer initial UCTZAR to LPs, traders, and pool
    params = client.suggested_params()
    uctzar_transfer_amount = 100000  # 0.1 UCTZAR
    for address in [lp1_address, lp2_address, trader1_address, trader2_address, pool_address]:
        txn = AssetTransferTxn(creator_address, params, address, uctzar_transfer_amount, uctzar_id)
        signed_txn = txn.sign(creator_private_key)
        client.send_transaction(signed_txn)
        wait_for_confirmation(client, signed_txn.get_txid())

    # Create liquidity pool
    pool = LiquidityPool(100000, 200000)  # 0.1 ALGO = 0.2 UCTZAR

    return jsonify({"success": True, "message": "Creator funded and UCTZAR created"})


@app.route('/add_liquidity', methods=['POST'])
def add_liquidity():
    lp_address = request.form['lp_address']
    algo_amount = int(request.form['algo_amount'])
    uctzar_amount = int(request.form['uctzar_amount'])

    if lp_address == lp1_address:
        lp_private_key = lp1_private_key
    elif lp_address == lp2_address:
        lp_private_key = lp2_private_key
    else:
        return jsonify({"error": "Invalid LP address"})

    try:
        tx_id = add_liquidity_atomic(client, lp_address, lp_private_key, pool_address, algo_amount, uctzar_amount,
                                     uctzar_id)
        pool.add_liquidity(algo_amount, uctzar_amount)
        return jsonify({"success": True, "message": f"Liquidity added. Transaction ID: {tx_id}"})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/swap', methods=['POST'])
def swap():
    trader_address = request.form['trader_address']
    amount_in = int(request.form['amount_in'])
    asset_in = request.form['asset_in']

    if trader_address == trader1_address:
        trader_private_key = trader1_private_key
    elif trader_address == trader2_address:
        trader_private_key = trader2_private_key
    else:
        return jsonify({"error": "Invalid trader address"})

    try:
        if asset_in == 'ALGO':
            amount_out = int(pool.swap_algo_to_uctzar(amount_in))
            tx_id = swap_atomic(client, trader_address, trader_private_key, pool_address, pool_private_key, amount_in,
                                0, amount_out, uctzar_id)
        else:
            amount_out = int(pool.swap_uctzar_to_algo(amount_in))
            tx_id = swap_atomic(client, trader_address, trader_private_key, pool_address, pool_private_key, amount_in,
                                uctzar_id, amount_out, 0)

        return jsonify(
            {"success": True, "message": f"Swap completed. Transaction ID: {tx_id}", "amount_out": amount_out})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/pool_info', methods=['GET'])
def pool_info():
    if pool is None:
        return jsonify({"error": "Pool not initialized"})

    return jsonify({
        "algo_amount": pool.algo_amount,
        "uctzar_amount": pool.uctzar_amount,
        "lp_tokens": pool.lp_tokens,
        "fees": pool.fees
    })


if __name__ == '__main__':
    app.run(debug=True)