import re
import pandas as pd
import hashlib
from datetime import datetime
from decimal import Decimal
from django.core.exceptions import ValidationError
from pages.models import Transaction, UploadedFile

# Regular Expression Patterns for NayaPay Description Parsing
PATTERNS = {
    # POS: "Paid to MERCHANT CITY PK|Visa xxxx1234"
    "pos": re.compile(
        r"Paid to\s+(?P<counterparty>.+?)\|(?:Visa|Mastercard|UnionPay)\s+(?:xxxx)?(?P<card_suffix>\d{4})",
        re.IGNORECASE
    ),
    # Raast/IBFT: "Incoming/Outgoing fund transfer from/to NAME\nBANK-SUFFIX|..."
    "transfer_in": re.compile(
        r"Incoming fund transfer from\s+(?P<counterparty>.+?)(?:\n|\\n)"
        r"(?P<bank_platform>[^-|]+)-(?P<account_suffix>\w+)\|"
        r"(?:Nickname:\s*\w+\s*(?:\n|\\n))?"
        r"Transaction ID\s+(?P<transaction_id>\S+)",
        re.IGNORECASE | re.DOTALL
    ),
    "transfer_out": re.compile(
        r"Outgoing fund transfer to\s+(?P<counterparty>.+?)(?:\n|\\n)"
        r"(?P<bank_platform>[^-|]+)-(?P<account_suffix>\w+)\|"
        r"(?:Nickname:\s*\w+\s*(?:\n|\\n))?"
        r"Transaction ID\s+(?P<transaction_id>\S+)",
        re.IGNORECASE | re.DOTALL
    ),
    # Cash Withdrawal: "Cash Withdrawn at ATM|Visa xxxx3968, 25,000.00 PKR"
    "cash_withdrawal": re.compile(
        r"Cash Withdrawn at ATM\|(?:Visa|Mastercard|UnionPay)\s+(?:xxxx)?(?P<card_suffix>\d{4})",
        re.IGNORECASE
    ),
    # Peer to Peer: "Money sent to NAME|(user@nayapay)\nNayaPay xxxx123"
    "p2p_sent": re.compile(
        r"Money sent to\s+(?P<counterparty>.+?)\|\((?P<nayapay_username>[^)]+)\)"
        r"(?:\n|\\n)NayaPay\s+(?:xxxx)?(?P<account_suffix>\w+)",
        re.IGNORECASE | re.DOTALL
    ),
    "p2p_received": re.compile(
        r"Money received from\s+(?P<counterparty>.+?)\|\((?P<nayapay_username>[^)]+)\)"
        r"(?:\n|\\n)NayaPay\s+(?:xxxx)?(?P<account_suffix>\w+)",
        re.IGNORECASE | re.DOTALL
    ),
    # Bill Payment: "Bill Paid for SERVICE\nConsumer No. 12345|Transaction ID ..."
    "bill_payment": re.compile(
        r"Bill Paid for\s+(?P<counterparty>.+?)(?:\n|\\n)"
        r"Consumer No\.\s*(?P<consumer_no>\S+)\|"
        r"Transaction ID\s+(?P<transaction_id>\S+)",
        re.IGNORECASE | re.DOTALL
    ),
    # Mobile Top-up: "Zong Top-up for 03123456789\nTransaction ID ..."
    "mobile_topup": re.compile(
        r"(?P<counterparty>\w+)\s+Top-up for\s+(?P<phone_number>\d+)"
        r"(?:\n|\\n)Transaction ID\s+(?P<transaction_id>\S+)",
        re.IGNORECASE | re.DOTALL
    ),
}

def parse_nayapay_description(txn_type, raw_desc):
    """
    Scans the free-text description of a NayaPay transaction using pre-compiled
    regex patterns to extract merchant/counterparty names, payment channels,
    phone numbers, utility consumer numbers, and unique transaction references.
    """
    result = {
        "merchant_name": None,
        "transaction_type": txn_type,
        "notes": None,
        "transaction_id": None,
    }
    if not raw_desc:
        return result

    # Standardize newline formatting in description string
    desc = raw_desc.replace("\\n", "\n")

    # POS transaction extraction
    if txn_type == "POS":
        m = PATTERNS["pos"].search(desc)
        if m:
            full_merchant = m.group("counterparty").strip()
            parts = full_merchant.rsplit(" ", 2)
            if len(parts) >= 3 and parts[-1].upper() == "PK":
                result["merchant_name"] = " ".join(parts[:-2])
            else:
                result["merchant_name"] = full_merchant
            result["transaction_type"] = "Visa POS"
            result["notes"] = f"Card: **** {m.group('card_suffix')}"
        return result

    # Incoming Bank Transfer
    if "In" in txn_type or txn_type == "IBFT In" or txn_type == "Raast In":
        m = PATTERNS["transfer_in"].search(desc)
        if m:
            result["merchant_name"] = m.group("counterparty").strip()
            result["transaction_type"] = f"Transfer In ({m.group('bank_platform').strip()})"
            result["transaction_id"] = m.group("transaction_id").strip()
            result["notes"] = f"Account: **** {m.group('account_suffix')}"
        return result

    # Outgoing Bank Transfer
    if "Out" in txn_type or txn_type == "IBFT Out" or txn_type == "Raast Out":
        m = PATTERNS["transfer_out"].search(desc)
        if m:
            result["merchant_name"] = m.group("counterparty").strip()
            result["transaction_type"] = f"Transfer Out ({m.group('bank_platform').strip()})"
            result["transaction_id"] = m.group("transaction_id").strip()
            result["notes"] = f"Account: **** {m.group('account_suffix')}"
        return result

    # ATM Cash Withdrawal
    if txn_type == "Cash Withdrawal":
        m = PATTERNS["cash_withdrawal"].search(desc)
        if m:
            result["merchant_name"] = "ATM Withdrawal"
            result["transaction_type"] = "ATM Withdrawal"
            result["notes"] = f"Card: **** {m.group('card_suffix')}"
        return result

    # Peer to Peer Transfers
    if txn_type == "Peer to Peer":
        m = PATTERNS["p2p_sent"].search(desc)
        if m:
            result["merchant_name"] = m.group("counterparty").strip()
            result["transaction_type"] = "P2P Out (NayaPay)"
            result["notes"] = f"Recipient ID: {m.group('nayapay_username').strip()}"
            return result

        m = PATTERNS["p2p_received"].search(desc)
        if m:
            result["merchant_name"] = m.group("counterparty").strip()
            result["transaction_type"] = "P2P In (NayaPay)"
            result["notes"] = f"Sender ID: {m.group('nayapay_username').strip()}"
            return result

    # Utility Bill Payment
    if txn_type == "Bill Payment":
        m = PATTERNS["bill_payment"].search(desc)
        if m:
            result["merchant_name"] = m.group("counterparty").strip()
            result["transaction_type"] = "Bill Payment"
            result["transaction_id"] = m.group("transaction_id").strip()
            result["notes"] = f"Consumer No: {m.group('consumer_no').strip()}"
        return result

    # Mobile Telecom Top-up
    if txn_type == "Mobile Top-up":
        m = PATTERNS["mobile_topup"].search(desc)
        if m:
            result["merchant_name"] = m.group("counterparty").strip() + " Top-up"
            result["transaction_type"] = "Mobile Top-up"
            result["transaction_id"] = m.group("transaction_id").strip()
            result["notes"] = f"Mobile No: {m.group('phone_number').strip()}"
        return result

    return result


def process_nayapay_csv(file_path, user, uploaded_file_instance):
    """
    Parses a NayaPay exported CSV statement using Pandas, cleans localized data formatting,
    runs regex metadata parsing, filters duplicates in memory, and bulk-creates
    database entries.
    """
    # 1. Dynamically locate the true header row to bypass any header metadata blocks
    skip_rows = 0
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        for idx, line in enumerate(f):
            # Looks for standard NayaPay column identifiers (case-insensitive)
            if 'amount' in line.lower() and ('description' in line.lower() or 'narration' in line.lower()):
                skip_rows = idx
                break

    # 2. Load the CSV into a Pandas DataFrame starting from the identified data boundary
    df = pd.read_csv(file_path, skiprows=skip_rows)
    
    # Strip whitespace and convert to lowercase for case-insensitive mapping
    df.columns = df.columns.str.strip().str.lower()

    # 3. Dynamic Column Mapping Dictionary to standard database targets
    column_mapping = {
        'date & time': 'date',
        'transaction date': 'date',
        'date': 'date',
        'timestamp': 'date',
        'description': 'description',
        'narration': 'description',
        'remarks': 'description',
        'amount': 'amount',
        'amount(pkr)': 'amount',
        'type': 'type'
    }

    # Rename columns to standardized internal processing names
    df = df.rename(columns={k: v for k, v in column_mapping.items() if k in df.columns})

    # Verify that all essential structural dimensions are satisfied
    required_fields = ['date', 'description', 'amount']
    missing_fields = [field for field in required_fields if field not in df.columns]
    if missing_fields:
        raise ValidationError(f"Invalid CSV structure. Missing required columns: {missing_fields}")

    # Fetch existing transaction hashes and IDs for duplicate verification
    existing_hashes = set(
        Transaction.objects.filter(user=user).values_list('tx_hash', flat=True)
    )
    existing_tx_ids = set(
        Transaction.objects.filter(user=user, transaction_id__isnull=False).values_list('transaction_id', flat=True)
    )

    transactions_to_create = []
    skipped_duplicates = 0

    # 4. Iterate over the DataFrame values and perform data scrubbing
    for _, row in df.iterrows():
        raw_amount = str(row['amount']).strip()
        raw_date = str(row['date']).strip()
        raw_description = str(row['description']).strip()
        raw_type = str(row['type']).strip() if 'type' in df.columns else 'Unknown'

        # Skip completely empty filler rows safely
        if pd.isna(row['amount']) or raw_amount == '':
            continue

        # Clean local currency string formatting elements (Rs., commas, spaces)
        cleaned_amount = re.sub(r'[^\d\.\-]', '', raw_amount)
        
        try:
            amount_decimal = Decimal(cleaned_amount)
        except Exception:
            # Fallback configuration to capture edge case invalid structural values
            continue

        # Dynamic Timestamp Normalization Engine
        parsed_date = None
        date_formats = [
            '%Y-%m-%d %H:%M:%S', '%d-%m-%Y %H:%M:%S', '%d/%m/%Y %H:%M:%S', 
            '%b %d, %Y', '%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y',
            '%Y-%m-%d %H:%M', '%d-%m-%Y %H:%M', '%d/%m/%Y %H:%M'
        ]
        for fmt in date_formats:
            try:
                parsed_dt = datetime.strptime(raw_date, fmt)
                parsed_date = parsed_dt.date()
                break
            except ValueError:
                continue

        if not parsed_date:
            # Fallback default if row timestamps fail processing structures
            parsed_date = datetime.now().date()

        # Parse the description to extract key structured metadata fields
        parsed_info = parse_nayapay_description(raw_type, raw_description)
        transaction_id = parsed_info['transaction_id']

        # Calculate transaction signature hash (SHA-256)
        raw_hash_string = f"{user.id}|{parsed_date}|{amount_decimal}|{raw_description.strip().lower()}"
        tx_hash = hashlib.sha256(raw_hash_string.encode('utf-8')).hexdigest()

        # Deduplication check
        if transaction_id and transaction_id in existing_tx_ids:
            skipped_duplicates += 1
            continue
        if tx_hash in existing_hashes:
            skipped_duplicates += 1
            continue

        # Cache new records locally to prevent intra-batch duplication
        if transaction_id:
            existing_tx_ids.add(transaction_id)
        existing_hashes.add(tx_hash)

        # Assemble individual item payloads for optimal single-batch database execution
        transactions_to_create.append(
            Transaction(
                user=user,
                uploaded_file=uploaded_file_instance,
                date=parsed_date,
                description=raw_description,
                amount=amount_decimal,
                merchant_name=parsed_info['merchant_name'][:100] if parsed_info['merchant_name'] else None,
                transaction_type=parsed_info['transaction_type'][:50] if parsed_info['transaction_type'] else None,
                notes=parsed_info['notes'],
                transaction_id=transaction_id[:100] if transaction_id else None,
                tx_hash=tx_hash,
                category=None
            )
        )

    # 5. Execute unified bulk saving configuration to optimize database performance
    if transactions_to_create:
        Transaction.objects.bulk_create(transactions_to_create)
        
    return len(transactions_to_create), skipped_duplicates
