"""CLI entry point.

Examples:
    python run.py seed                       # load bundled sample leads
    python run.py search "plumber Austin TX" # search Google Places (needs API key)
    python run.py generate 1                 # generate site + pitch for lead id 1
    python run.py generate-all               # generate for every lead without one
    python run.py list                       # list leads
"""
import sys

from dotenv import load_dotenv
load_dotenv()

from src import finder, generator, storage


def cmd_seed():
    storage.init_db()
    n = finder.load_sample_leads()
    print(f"Loaded {n} sample leads.")


def cmd_search(query):
    storage.init_db()
    leads = finder.search_google_places(query, max_results=20)
    print(f"Added {len(leads)} new leads from Google Places.")


def cmd_generate(lead_id):
    result = generator.generate_for_lead(int(lead_id))
    print(f"Generated for lead {lead_id}")
    print(f"  Site: {result['site_path']}")
    print(f"\nEmail pitch:\n{result['email_pitch']}\n")
    print(f"Phone script:\n{result['phone_script']}")


def cmd_generate_all():
    leads = [lead for lead in storage.list_leads() if not lead.get("site_html")]
    print(f"Generating for {len(leads)} leads...")
    for lead in leads:
        try:
            generator.generate_for_lead(lead["id"])
            print(f"  ✓ {lead['business_name']}")
        except Exception as e:
            print(f"  ✗ {lead['business_name']}: {e}")


def cmd_list():
    leads = storage.list_leads(only_no_website=False)
    if not leads:
        print("No leads. Run `python run.py seed` first.")
        return
    for lead in leads:
        marks = []
        if lead.get("site_html"):
            marks.append("site")
        if lead.get("email_pitch"):
            marks.append("email")
        tag = f" [{', '.join(marks)}]" if marks else ""
        print(f"{lead['id']:3}  {lead['status']:12}  {lead['business_name']}{tag}")


COMMANDS = {
    "seed": cmd_seed,
    "search": cmd_search,
    "generate": cmd_generate,
    "generate-all": cmd_generate_all,
    "list": cmd_list,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    args = sys.argv[2:]
    COMMANDS[cmd](*args)


if __name__ == "__main__":
    main()
