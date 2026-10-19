"""Sales regions derived from the country (accounts carry a country; an account's own region field wins)."""
import re

REGIONS = ("Americas", "Europe", "Middle East & Africa", "Asia Pacific")

# matched on the whole country name, as BMC writes it (e.g. "USA", "Taiwan, Republic of China")
_PHRASES = {
    "Americas": ["united states of america", "united states", "costa rica", "el salvador", "dominican republic",
                 "puerto rico", "trinidad and tobago", "usa", "us", "canada", "mexico", "brazil", "argentina",
                 "chile", "colombia", "peru", "uruguay", "paraguay", "bolivia", "ecuador", "venezuela", "panama",
                 "guatemala", "honduras", "nicaragua", "jamaica", "bahamas", "barbados"],
    "Europe": ["united kingdom", "great britain", "czech republic", "bosnia and herzegovina", "north macedonia",
               "russian federation", "uk", "england", "scotland", "ireland", "france", "germany", "spain",
               "portugal", "italy", "netherlands", "belgium", "luxembourg", "switzerland", "austria",
               "liechtenstein", "monaco", "sweden", "norway", "denmark", "finland", "iceland", "poland", "czechia",
               "slovakia", "hungary", "romania", "bulgaria", "greece", "cyprus", "malta", "croatia", "slovenia",
               "serbia", "montenegro", "albania", "estonia", "latvia", "lithuania", "ukraine", "moldova",
               "belarus", "russia", "turkey", "türkiye", "azerbaijan", "georgia", "armenia", "kazakhstan"],
    "Middle East & Africa": ["saudi arabia", "united arab emirates", "south africa", "ivory coast", "côte d'ivoire",
                             "uae", "qatar", "kuwait", "bahrain", "oman", "yemen", "jordan", "lebanon", "israel",
                             "iraq", "iran", "syria", "palestine", "egypt", "morocco", "algeria", "tunisia",
                             "libya", "nigeria", "kenya", "ghana", "ethiopia", "tanzania", "uganda", "rwanda",
                             "senegal", "cameroon", "angola", "mozambique", "zambia", "zimbabwe", "botswana",
                             "namibia", "mauritius", "madagascar", "sudan"],
    "Asia Pacific": ["taiwan, republic of china", "korea, republic of", "hong kong", "south korea", "new zealand",
                     "sri lanka", "viet nam", "india", "china", "macau", "taiwan", "japan", "korea", "singapore",
                     "malaysia", "indonesia", "thailand", "vietnam", "philippines", "australia", "pakistan",
                     "bangladesh", "nepal", "myanmar", "cambodia", "laos", "brunei", "mongolia", "fiji"],
}
_LOOKUP = {n: region for region, names in _PHRASES.items() for n in names}


def region_of(country: str | None, account_region: str | None = None) -> str:
    """Region for an account: its own region when set, else from the country, else "Other"."""
    if account_region and account_region.strip():
        r = account_region.strip()
        return next((x for x in REGIONS if x.lower() == r.lower()), r)
    c = re.sub(r"\s+", " ", (country or "").strip().lower())
    return _LOOKUP.get(c, "Other") if c else "Other"
