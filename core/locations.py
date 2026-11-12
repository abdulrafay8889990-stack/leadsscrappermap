"""Countries, their major cities and the areas of very large cities.

Used by the city picker in the GUI and to work out the city / country of a search
location such as "Clifton, Karachi", "Lahore, Pakistan" or "Austin, TX, USA".
Google Maps returns at most ~120 places per search, so big cities can be expanded into
areas to get many more leads.
"""
from __future__ import annotations

import re

COUNTRIES: dict[str, list[str]] = {
    "Pakistan": ["Karachi", "Lahore", "Islamabad", "Rawalpindi", "Faisalabad", "Multan", "Peshawar", "Quetta",
                 "Hyderabad", "Sialkot", "Gujranwala", "Bahawalpur", "Sargodha", "Sukkur", "Abbottabad", "Mardan"],
    "United Arab Emirates": ["Dubai", "Abu Dhabi", "Sharjah", "Ajman", "Ras Al Khaimah", "Fujairah", "Al Ain",
                             "Umm Al Quwain"],
    "Saudi Arabia": ["Riyadh", "Jeddah", "Mecca", "Medina", "Dammam", "Khobar", "Dhahran", "Taif", "Tabuk", "Abha"],
    "Qatar": ["Doha", "Al Wakrah", "Al Rayyan", "Lusail", "Al Khor"],
    "Kuwait": ["Kuwait City", "Hawalli", "Salmiya", "Farwaniya", "Jahra", "Fahaheel"],
    "Oman": ["Muscat", "Salalah", "Sohar", "Nizwa", "Sur"],
    "Bahrain": ["Manama", "Muharraq", "Riffa", "Hamad Town", "Isa Town"],
    "India": ["Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai", "Kolkata", "Pune", "Ahmedabad", "Jaipur",
              "Surat", "Lucknow", "Kochi", "Chandigarh", "Indore", "Nagpur", "Goa"],
    "Bangladesh": ["Dhaka", "Chittagong", "Khulna", "Rajshahi", "Sylhet", "Comilla"],
    "Sri Lanka": ["Colombo", "Kandy", "Galle", "Negombo", "Jaffna"],
    "United Kingdom": ["London", "Manchester", "Birmingham", "Leeds", "Glasgow", "Liverpool", "Bristol",
                       "Edinburgh", "Sheffield", "Leicester", "Nottingham", "Cardiff", "Newcastle", "Bradford",
                       "Coventry", "Belfast"],
    "Ireland": ["Dublin", "Cork", "Galway", "Limerick", "Waterford"],
    "United States": ["New York, NY", "Los Angeles, CA", "Chicago, IL", "Houston, TX", "Phoenix, AZ",
                      "Philadelphia, PA", "San Antonio, TX", "San Diego, CA", "Dallas, TX", "Austin, TX",
                      "Jacksonville, FL", "San Jose, CA", "Columbus, OH", "Charlotte, NC", "Indianapolis, IN",
                      "San Francisco, CA", "Seattle, WA", "Denver, CO", "Boston, MA", "Nashville, TN",
                      "Las Vegas, NV", "Atlanta, GA", "Miami, FL", "Orlando, FL", "Tampa, FL", "Detroit, MI",
                      "Minneapolis, MN", "Portland, OR", "Sacramento, CA", "Raleigh, NC"],
    "Canada": ["Toronto", "Montreal", "Vancouver", "Calgary", "Edmonton", "Ottawa", "Winnipeg", "Mississauga",
               "Brampton", "Hamilton", "Quebec City", "Surrey", "Halifax", "Victoria"],
    "Australia": ["Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide", "Gold Coast", "Canberra", "Newcastle",
                  "Hobart", "Darwin"],
    "New Zealand": ["Auckland", "Wellington", "Christchurch", "Hamilton", "Tauranga", "Dunedin"],
    "Germany": ["Berlin", "Hamburg", "Munich", "Cologne", "Frankfurt", "Stuttgart", "Düsseldorf", "Leipzig",
                "Dortmund", "Essen"],
    "France": ["Paris", "Marseille", "Lyon", "Toulouse", "Nice", "Nantes", "Strasbourg", "Bordeaux", "Lille"],
    "Netherlands": ["Amsterdam", "Rotterdam", "The Hague", "Utrecht", "Eindhoven", "Groningen"],
    "Spain": ["Madrid", "Barcelona", "Valencia", "Seville", "Malaga", "Bilbao", "Zaragoza"],
    "Italy": ["Rome", "Milan", "Naples", "Turin", "Florence", "Bologna", "Venice"],
    "Turkey": ["Istanbul", "Ankara", "Izmir", "Antalya", "Bursa", "Adana"],
    "Malaysia": ["Kuala Lumpur", "Penang", "Johor Bahru", "Petaling Jaya", "Shah Alam", "Kota Kinabalu",
                 "Kuching", "Ipoh", "Malacca"],
    "Singapore": ["Singapore"],
    "Indonesia": ["Jakarta", "Surabaya", "Bandung", "Medan", "Bali", "Semarang", "Yogyakarta"],
    "Philippines": ["Manila", "Quezon City", "Cebu City", "Davao City", "Makati", "Taguig"],
    "South Africa": ["Johannesburg", "Cape Town", "Durban", "Pretoria", "Port Elizabeth", "Bloemfontein"],
    "Nigeria": ["Lagos", "Abuja", "Port Harcourt", "Ibadan", "Kano", "Benin City"],
    "Kenya": ["Nairobi", "Mombasa", "Kisumu", "Nakuru", "Eldoret"],
    "Egypt": ["Cairo", "Alexandria", "Giza", "Sharm El Sheikh", "Hurghada", "Mansoura"],
}

# Areas of very large cities: searching each area separately gives far more than ~120 places.
CITY_AREAS: dict[str, list[str]] = {
    "Karachi": ["Clifton", "DHA", "Gulshan-e-Iqbal", "Gulistan-e-Jauhar", "North Nazimabad", "Nazimabad",
                "PECHS", "Saddar", "Tariq Road", "Bahadurabad", "Malir", "Korangi", "Federal B Area", "Gulberg",
                "Scheme 33", "Bahria Town Karachi"],
    "Lahore": ["DHA", "Gulberg", "Johar Town", "Model Town", "Bahria Town", "Wapda Town", "Garden Town",
               "Allama Iqbal Town", "Cantt", "Faisal Town", "Township", "Valencia Town"],
    "Islamabad": ["F-6", "F-7", "F-8", "F-10", "F-11", "G-9", "G-11", "I-8", "E-11", "Blue Area", "DHA",
                  "Bahria Town"],
    "Dubai": ["Downtown Dubai", "Dubai Marina", "Jumeirah", "Deira", "Bur Dubai", "Business Bay", "Al Barsha",
              "JLT", "Al Quoz", "Karama", "Mirdif", "Silicon Oasis"],
    "Riyadh": ["Al Olaya", "Al Malaz", "Al Sulimaniyah", "Al Nakheel", "Al Yasmin", "Al Rawdah", "Al Murabba",
               "Al Wurud"],
    "London": ["Westminster", "Camden", "Islington", "Hackney", "Shoreditch", "Kensington", "Chelsea", "Brixton",
               "Croydon", "Ealing", "Wembley", "Stratford", "Greenwich", "Hammersmith"],
    "New York, NY": ["Manhattan", "Brooklyn", "Queens", "Bronx", "Staten Island", "Harlem", "Williamsburg",
                     "Astoria"],
    "Los Angeles, CA": ["Downtown Los Angeles", "Hollywood", "Santa Monica", "Beverly Hills", "Pasadena",
                        "Burbank", "Glendale", "Long Beach", "Venice", "Koreatown", "Silver Lake", "Culver City"],
    "Chicago, IL": ["The Loop", "River North", "Lincoln Park", "Wicker Park", "Lakeview", "Hyde Park",
                    "West Loop", "Logan Square", "Evanston", "Oak Park"],
    "Houston, TX": ["Downtown Houston", "Midtown Houston", "Montrose", "The Heights", "Galleria", "Katy",
                    "Sugar Land", "Pearland", "The Woodlands"],
    "Dallas, TX": ["Downtown Dallas", "Uptown Dallas", "Deep Ellum", "Plano", "Irving", "Frisco", "Richardson",
                   "Garland"],
    "Miami, FL": ["Downtown Miami", "Brickell", "Wynwood", "Miami Beach", "Coral Gables", "Doral", "Hialeah",
                  "Little Havana"],
    "Manchester": ["Manchester City Centre", "Salford", "Stockport", "Trafford", "Didsbury", "Oldham", "Bolton",
                   "Rochdale"],
    "Birmingham": ["Birmingham City Centre", "Edgbaston", "Solihull", "Sutton Coldfield", "Moseley",
                   "Harborne", "Erdington", "Small Heath"],
    "Toronto": ["Downtown Toronto", "North York", "Scarborough", "Etobicoke", "East York", "Yorkville",
                "Liberty Village"],
    "Vancouver": ["Downtown Vancouver", "Kitsilano", "Burnaby", "Richmond", "North Vancouver", "Mount Pleasant",
                  "Gastown", "Coquitlam"],
    "Sydney": ["Sydney CBD", "Parramatta", "Bondi", "Surry Hills", "Chatswood", "North Sydney", "Newtown",
               "Bankstown", "Liverpool NSW"],
    "Melbourne": ["Melbourne CBD", "Fitzroy", "St Kilda", "Richmond VIC", "South Yarra", "Brunswick",
                  "Footscray", "Dandenong", "Box Hill"],
    "Mumbai": ["Andheri", "Bandra", "Powai", "Juhu", "Colaba", "Dadar", "Thane", "Navi Mumbai", "Borivali"],
    "Delhi": ["Connaught Place", "Saket", "Hauz Khas", "Lajpat Nagar", "Karol Bagh", "Dwarka", "Rohini",
              "Vasant Kunj"],
}

COUNTRY_ALIASES = {"usa": "United States", "us": "United States", "united states of america": "United States",
                   "uk": "United Kingdom", "england": "United Kingdom", "uae": "United Arab Emirates",
                   "ksa": "Saudi Arabia"}
_COUNTRY_NAMES = {name.lower(): name for name in COUNTRIES} | COUNTRY_ALIASES
_CITY_TO_COUNTRY = {city.split(",")[0].strip().lower(): country
                    for country, cities in COUNTRIES.items() for city in cities}
_STATE_CODE_RE = re.compile(r"^[A-Z]{2}$")


def city_names() -> set[str]:
    """Every known city name (lower case) - used to ignore city words inside business names."""
    return set(_CITY_TO_COUNTRY)


def location_lines(country: str, cities: list[str], expand_areas: bool) -> list[str]:
    """Picker selection -> lines for the Locations box, e.g. 'Clifton, Karachi, Pakistan'."""
    lines = []
    for city in cities:
        if expand_areas and city in CITY_AREAS:
            lines += [f"{area}, {city}, {country}" for area in CITY_AREAS[city]]
        else:
            lines.append(f"{city}, {country}")
    return lines


def parse_location(location: str) -> tuple[str, str]:
    """'Clifton, Karachi, Pakistan' -> ('Karachi', 'Pakistan'); 'Austin, TX, USA' -> ('Austin', 'United States');
    'Karachi' -> ('Karachi', 'Pakistan'); unknown places keep their last part as the city."""
    parts = [p.strip() for p in (location or "").split(",") if p.strip()]
    country = ""
    if parts and parts[-1].lower() in _COUNTRY_NAMES:
        country = _COUNTRY_NAMES[parts.pop().lower()]
    if len(parts) >= 2 and _STATE_CODE_RE.match(parts[-1]):  # US state code: "Austin, TX"
        parts.pop()
    # Prefer a part we know is a city ("Clifton, Karachi" -> Karachi), else the last part.
    city = next((p for p in reversed(parts) if p.lower() in _CITY_TO_COUNTRY), parts[-1] if parts else "")
    if not country and city:
        country = _CITY_TO_COUNTRY.get(city.lower(), "")
    return city, country
