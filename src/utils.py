import logging
from typing import List, Dict

def configure_logging(log_file=None):
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        filename=log_file,
        filemode='a' if log_file else None
    )

def deduplicate_opportunities(opps: List[Dict]) -> List[Dict]:
    seen = set()
    deduped = []
    for item in opps:
        bid = item.get('bidding_id') or item.get('opp_id') or item.get('id')
        if bid and bid not in seen:
            deduped.append(item)
            seen.add(bid)
    return deduped
