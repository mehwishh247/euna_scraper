import re

def clean_opportunity(raw, agency=None):
    '''
    Takes a raw opportunity dict (from scraper) and agency dict.
    Returns cleaned dict with schema for Mongo insertion.
    '''
    result = {
        'organization_name': raw.get('organization_name') or (agency.get('name') if agency else raw.get('organization', None)),
        'bidding_id': raw.get('id') or raw.get('opp_id') or None,
        'opportunity_name': raw.get('name') or raw.get('title') or None,
        'description': raw.get('description') or raw.get('details') or None,
        'application_instructions': raw.get('how_to_apply') or None,
        'application_url': raw.get('apply_url') or raw.get('application_url') or None,
        'deadline': clean_deadline(raw.get('deadline') or raw.get('due_date')),
    }
    # Fill missing with null
    for k in result:
        if result[k] in ('', [], {}, None):
            result[k] = None
    # Optionally include the raw data for debugging
    result['raw_data'] = raw
    return result

def clean_deadline(deadline):
    if not deadline or deadline in ('', None):
        return None
    # Normalize YYYY-MM-DD, or best effort ISO
    match = re.search(r'(\d{4}-\d{2}-\d{2})', str(deadline))
    if match:
        return match.group(1)
    return str(deadline).strip()

def clean_all_opportunities(raw_list):
    """Process a list of raw opportunities, return cleaned list."""
    cleaned = []
    for raw in raw_list:
        # organization_name is already in raw from scraper
        agency = {'name': raw.get('organization_name')} if raw.get('organization_name') else None
        cleaned.append(clean_opportunity(raw, agency))
    return cleaned
