# EUNA BonfireHub Agency Opportunities Scraper

## Objective
Automate the extraction, cleaning, and MongoDB preparation of bidding opportunities from https://vendor.bonfirehub.com/ for selected agencies.

---

## Prerequisites
- Docker & docker-compose (recommended run mode)
- Or: Python 3.12, Poetry, Chromium
- MongoDB for data import (optional)

## .env Configuration
Place a `.env` file at project root:
```
EMAIL=your_account_email@domain.com
PASSWORD=your_account_password
MONGO_URI=mongodb://root:example@localhost:27017/
MONGO_DB=euna
```

---

## Usage
### LOCALLY (Python)
```bash
poetry install
python src/scraper.py
```
Output: 
- `data/open_opportunities.json`
- `data/past_opportunities.json`

### DOCKERIZED
```bash
docker-compose -f docker/docker-compose.yml up --build
```

---

### Customization Tips
- Update agency filtering letters or limits in `src/scraper.py` (`AGENCY_PREFIXES`).
- To add/change proxies, edit the `PROXIES` variable in `src/scraper.py`.

### Troubleshooting
- **Captcha**: If too many opportunities fail to extract due to captchas, run with your own stable IP, increase delays, or intervene when prompted.
- **Missing Fields**: Check log output for missing or malformed entries—tweak selectors as the site evolves.

---

## Output
You will get two JSON files, ready to be imported into MongoDB, with this structure:
```json
[
  {
    "organization_name": "Dallas Fort Worth International Airport",
    "bidding_id": "DFW14494",
    "opportunity_name": "Some Bid Title",
    "description": "Project overview here...",
    "application_instructions": null,
    "application_url": "https://dfwairport.bonfirehub.com/opportunities/212116",
    "deadline": "2025-12-10",
    "raw_data": { ...all original detail fields... }
  }
]
```

---

**Developer:**
- `github.com/mehwishh247`
- For scraper tuning, open an issue.
