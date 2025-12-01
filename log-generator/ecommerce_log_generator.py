#!/usr/bin/env python3
"""
Smart E-Commerce Log Generator for Anomaly Detection Framework.

Simulates a realistic e-commerce website with:
- Products, categories, and inventory
- User sessions and shopping behavior
- Cart operations, checkout, payments
- Realistic traffic patterns (sales events, seasonal peaks, business hours)
- High-volume data generation (10,000+ requests per hour at peak)

Generates logs to the 'ecommerce-logs' index in Elasticsearch.

ULTRA-OPTIMIZED for MAXIMUM throughput:
- Direct HTTP to ES Bulk API (bypasses elasticsearch-py overhead)
- orjson: 10x faster JSON serialization
- uvloop: faster event loop (Linux)
- aiohttp: async HTTP with connection pooling
- multiprocessing: parallel document generation across CPU cores
"""
import os
import sys
import time
import random
import signal
import logging
import hashlib
import asyncio
import aiohttp
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Tuple, Generator, AsyncGenerator, Any
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing as mp
from faker import Faker

# Use orjson for 10x faster JSON serialization
try:
    import orjson
    def fast_json_dumps(obj):
        return orjson.dumps(obj, option=orjson.OPT_NAIVE_UTC | orjson.OPT_UTC_Z)
    def fast_json_dumps_str(obj):
        return orjson.dumps(obj, option=orjson.OPT_NAIVE_UTC | orjson.OPT_UTC_Z).decode('utf-8')
    ORJSON_ENABLED = True
except ImportError:
    import json
    def fast_json_dumps(obj):
        return json.dumps(obj, default=str).encode('utf-8')
    def fast_json_dumps_str(obj):
        return json.dumps(obj, default=str)
    ORJSON_ENABLED = False

# Try to use uvloop for faster async (Linux only)
try:
    import uvloop
    uvloop.install()
    UVLOOP_ENABLED = True
except ImportError:
    UVLOOP_ENABLED = False

# Silence ES HTTP request logging (massive performance boost)
logging.getLogger("elastic_transport.transport").setLevel(logging.WARNING)
logging.getLogger("elasticsearch").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# =============================================================================
# CONFIGURATION
# =============================================================================
ES_HOST = os.getenv("ES_HOST", "http://elasticsearch-dataset:9200")
INDEX_NAME = os.getenv("INDEX_NAME", "ecommerce-logs")

# Historical data settings - MASSIVE DATA GENERATION
HISTORICAL_DAYS = int(os.getenv("HISTORICAL_DAYS", "365"))
HISTORICAL_BATCH_SIZE = int(os.getenv("HISTORICAL_BATCH_SIZE", "10000"))

# Traffic volume settings (requests per hour at base load)
BASE_REQUESTS_PER_HOUR = int(os.getenv("BASE_REQUESTS_PER_HOUR", "5000"))
PEAK_MULTIPLIER = float(os.getenv("PEAK_MULTIPLIER", "4.0"))  # Peak hours get 4x traffic

# Anomaly settings
HISTORICAL_ANOMALY_RATE = float(os.getenv("HISTORICAL_ANOMALY_RATE", "0.015"))  # 1.5%

# Continuous generation settings
CONTINUOUS_INTERVAL = float(os.getenv("CONTINUOUS_INTERVAL", "1.0"))
LOGS_PER_INTERVAL_MIN = int(os.getenv("LOGS_PER_INTERVAL_MIN", "50"))
LOGS_PER_INTERVAL_MAX = int(os.getenv("LOGS_PER_INTERVAL_MAX", "150"))
CONTINUOUS_ANOMALY_RATE = float(os.getenv("CONTINUOUS_ANOMALY_RATE", "0.02"))

# Burst settings (flash sales, viral moments)
BURST_PROBABILITY = float(os.getenv("BURST_PROBABILITY", "0.03"))
BURST_SIZE_MIN = int(os.getenv("BURST_SIZE_MIN", "200"))
BURST_SIZE_MAX = int(os.getenv("BURST_SIZE_MAX", "1000"))

# Performance settings - MAXIMUM THROUGHPUT
NUM_WORKERS = int(os.getenv("NUM_WORKERS", "4"))  # Parallel workers for generation
BULK_THREAD_COUNT = int(os.getenv("BULK_THREAD_COUNT", "32"))  # Parallel bulk streams
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "10000"))  # Docs per bulk chunk (smaller = more parallelism)

# =============================================================================
# LOGGING SETUP
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# =============================================================================
# E-COMMERCE DATA MODEL
# =============================================================================
fake = Faker()
Faker.seed(42)  # Reproducible data

# Product Categories and Products
CATEGORIES = {
    "electronics": {
        "products": [
            {"id": "ELEC001", "name": "Wireless Headphones Pro", "price": 149.99, "popularity": 0.95},
            {"id": "ELEC002", "name": "Smart Watch Series X", "price": 299.99, "popularity": 0.90},
            {"id": "ELEC003", "name": "Bluetooth Speaker Mini", "price": 49.99, "popularity": 0.85},
            {"id": "ELEC004", "name": "USB-C Hub 7-in-1", "price": 39.99, "popularity": 0.70},
            {"id": "ELEC005", "name": "Wireless Mouse Ergonomic", "price": 29.99, "popularity": 0.75},
            {"id": "ELEC006", "name": "4K Webcam Pro", "price": 89.99, "popularity": 0.65},
            {"id": "ELEC007", "name": "Mechanical Keyboard RGB", "price": 119.99, "popularity": 0.80},
            {"id": "ELEC008", "name": "Portable SSD 1TB", "price": 99.99, "popularity": 0.72},
            {"id": "ELEC009", "name": "Noise Cancelling Earbuds", "price": 179.99, "popularity": 0.88},
            {"id": "ELEC010", "name": "Tablet Stand Adjustable", "price": 24.99, "popularity": 0.55},
        ],
        "weight": 30,  # 30% of traffic
    },
    "clothing": {
        "products": [
            {"id": "CLTH001", "name": "Premium Cotton T-Shirt", "price": 29.99, "popularity": 0.90},
            {"id": "CLTH002", "name": "Slim Fit Jeans", "price": 59.99, "popularity": 0.85},
            {"id": "CLTH003", "name": "Winter Jacket Waterproof", "price": 129.99, "popularity": 0.70},
            {"id": "CLTH004", "name": "Running Shoes Comfort", "price": 89.99, "popularity": 0.82},
            {"id": "CLTH005", "name": "Wool Sweater Classic", "price": 69.99, "popularity": 0.65},
            {"id": "CLTH006", "name": "Sport Leggings", "price": 44.99, "popularity": 0.78},
            {"id": "CLTH007", "name": "Canvas Sneakers", "price": 54.99, "popularity": 0.75},
            {"id": "CLTH008", "name": "Dress Shirt Formal", "price": 49.99, "popularity": 0.60},
        ],
        "weight": 25,
    },
    "home_garden": {
        "products": [
            {"id": "HOME001", "name": "Smart LED Bulb Pack", "price": 34.99, "popularity": 0.80},
            {"id": "HOME002", "name": "Memory Foam Pillow", "price": 49.99, "popularity": 0.75},
            {"id": "HOME003", "name": "Stainless Steel Cookware Set", "price": 149.99, "popularity": 0.65},
            {"id": "HOME004", "name": "Robot Vacuum Cleaner", "price": 299.99, "popularity": 0.70},
            {"id": "HOME005", "name": "Air Purifier HEPA", "price": 179.99, "popularity": 0.68},
            {"id": "HOME006", "name": "Weighted Blanket", "price": 79.99, "popularity": 0.72},
            {"id": "HOME007", "name": "Garden Tool Set", "price": 44.99, "popularity": 0.50},
        ],
        "weight": 20,
    },
    "beauty": {
        "products": [
            {"id": "BEAU001", "name": "Vitamin C Serum", "price": 29.99, "popularity": 0.88},
            {"id": "BEAU002", "name": "Hair Dryer Professional", "price": 79.99, "popularity": 0.75},
            {"id": "BEAU003", "name": "Makeup Brush Set", "price": 24.99, "popularity": 0.70},
            {"id": "BEAU004", "name": "Moisturizing Face Cream", "price": 39.99, "popularity": 0.82},
            {"id": "BEAU005", "name": "Electric Shaver", "price": 69.99, "popularity": 0.65},
            {"id": "BEAU006", "name": "Perfume Eau de Toilette", "price": 89.99, "popularity": 0.60},
        ],
        "weight": 15,
    },
    "sports": {
        "products": [
            {"id": "SPRT001", "name": "Yoga Mat Premium", "price": 34.99, "popularity": 0.85},
            {"id": "SPRT002", "name": "Dumbbell Set Adjustable", "price": 149.99, "popularity": 0.70},
            {"id": "SPRT003", "name": "Fitness Tracker Band", "price": 49.99, "popularity": 0.80},
            {"id": "SPRT004", "name": "Resistance Bands Set", "price": 19.99, "popularity": 0.75},
            {"id": "SPRT005", "name": "Water Bottle Insulated", "price": 24.99, "popularity": 0.90},
        ],
        "weight": 10,
    },
}

# Build weighted product list for random selection
WEIGHTED_PRODUCTS = []
for cat_name, cat_data in CATEGORIES.items():
    for product in cat_data["products"]:
        weight = int(cat_data["weight"] * product["popularity"] * 10)
        WEIGHTED_PRODUCTS.extend([(cat_name, product)] * weight)

# User behavior patterns
class UserIntent(Enum):
    BROWSE = "browse"           # Just looking
    SEARCH = "search"           # Active search
    COMPARE = "compare"         # Comparing products
    ADD_TO_CART = "add_to_cart" # Intent to buy
    CHECKOUT = "checkout"       # Ready to purchase
    SUPPORT = "support"         # Need help

# Endpoint templates for e-commerce operations
ENDPOINTS = {
    # Homepage & Navigation
    "homepage": {"path": "/", "method": "GET", "weight": 15},
    "category_list": {"path": "/categories", "method": "GET", "weight": 8},
    "category_view": {"path": "/categories/{category}", "method": "GET", "weight": 12},
    
    # Product Operations
    "product_list": {"path": "/api/v1/products", "method": "GET", "weight": 18},
    "product_detail": {"path": "/api/v1/products/{product_id}", "method": "GET", "weight": 20},
    "product_reviews": {"path": "/api/v1/products/{product_id}/reviews", "method": "GET", "weight": 8},
    "product_inventory": {"path": "/api/v1/products/{product_id}/inventory", "method": "GET", "weight": 3},
    
    # Search
    "search": {"path": "/api/v1/search", "method": "GET", "weight": 15},
    "search_suggestions": {"path": "/api/v1/search/suggestions", "method": "GET", "weight": 10},
    "search_filters": {"path": "/api/v1/search/filters", "method": "GET", "weight": 5},
    
    # Cart Operations
    "cart_view": {"path": "/api/v1/cart", "method": "GET", "weight": 10},
    "cart_add": {"path": "/api/v1/cart/items", "method": "POST", "weight": 8},
    "cart_update": {"path": "/api/v1/cart/items/{item_id}", "method": "PUT", "weight": 4},
    "cart_remove": {"path": "/api/v1/cart/items/{item_id}", "method": "DELETE", "weight": 3},
    
    # Checkout & Payment
    "checkout_init": {"path": "/api/v1/checkout", "method": "POST", "weight": 4},
    "checkout_shipping": {"path": "/api/v1/checkout/shipping", "method": "POST", "weight": 3},
    "checkout_payment": {"path": "/api/v1/checkout/payment", "method": "POST", "weight": 3},
    "order_confirm": {"path": "/api/v1/orders", "method": "POST", "weight": 2},
    "order_status": {"path": "/api/v1/orders/{order_id}", "method": "GET", "weight": 5},
    
    # User Account
    "user_login": {"path": "/api/v1/auth/login", "method": "POST", "weight": 6},
    "user_logout": {"path": "/api/v1/auth/logout", "method": "POST", "weight": 2},
    "user_register": {"path": "/api/v1/auth/register", "method": "POST", "weight": 2},
    "user_profile": {"path": "/api/v1/users/me", "method": "GET", "weight": 4},
    "user_orders": {"path": "/api/v1/users/me/orders", "method": "GET", "weight": 3},
    "user_wishlist": {"path": "/api/v1/users/me/wishlist", "method": "GET", "weight": 3},
    "user_wishlist_add": {"path": "/api/v1/users/me/wishlist", "method": "POST", "weight": 2},
    
    # Recommendations & Personalization
    "recommendations": {"path": "/api/v1/recommendations", "method": "GET", "weight": 8},
    "recently_viewed": {"path": "/api/v1/users/me/recently-viewed", "method": "GET", "weight": 4},
    
    # Support & Info
    "faq": {"path": "/faq", "method": "GET", "weight": 2},
    "contact": {"path": "/api/v1/support/contact", "method": "POST", "weight": 1},
    "track_order": {"path": "/api/v1/orders/{order_id}/tracking", "method": "GET", "weight": 3},
    
    # Static Assets & Health
    "health": {"path": "/health", "method": "GET", "weight": 1},
    "metrics": {"path": "/metrics", "method": "GET", "weight": 1},
}

# Build weighted endpoint list
WEIGHTED_ENDPOINTS = []
for name, data in ENDPOINTS.items():
    WEIGHTED_ENDPOINTS.extend([(name, data)] * data["weight"])

# Status codes with realistic distribution
STATUS_CODES_NORMAL = {
    200: 82,  # OK
    201: 5,   # Created
    204: 2,   # No Content
    301: 1,   # Redirect
    302: 1,   # Redirect
    304: 3,   # Not Modified
    400: 2,   # Bad Request
    401: 1,   # Unauthorized
    403: 0.5, # Forbidden
    404: 2,   # Not Found
    429: 0.5, # Rate Limited
}

STATUS_CODES_ANOMALY = [500, 502, 503, 504, 500, 500, 503, 500, 502, 503]

# User agents with device distribution
USER_AGENTS = {
    "mobile": [
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile Safari/604.1",
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/120.0.0.0 Mobile Safari/604.1",
    ],
    "desktop": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ],
    "bot": [
        "Googlebot/2.1 (+http://www.google.com/bot.html)",
        "Mozilla/5.0 (compatible; Bingbot/2.0; +http://www.bing.com/bingbot.htm)",
        "Mozilla/5.0 (compatible; AhrefsBot/7.0; +http://ahrefs.com/robot/)",
    ],
}

# Payment methods
PAYMENT_METHODS = ["credit_card", "debit_card", "paypal", "apple_pay", "google_pay", "klarna"]

# Geographic distribution (weighted by e-commerce activity)
GEO_DISTRIBUTION = [
    {"country": "US", "cities": ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix"], "weight": 40},
    {"country": "GB", "cities": ["London", "Manchester", "Birmingham", "Leeds", "Glasgow"], "weight": 15},
    {"country": "DE", "cities": ["Berlin", "Munich", "Hamburg", "Frankfurt", "Cologne"], "weight": 12},
    {"country": "FR", "cities": ["Paris", "Marseille", "Lyon", "Toulouse", "Nice"], "weight": 10},
    {"country": "CA", "cities": ["Toronto", "Montreal", "Vancouver", "Calgary", "Ottawa"], "weight": 8},
    {"country": "AU", "cities": ["Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide"], "weight": 6},
    {"country": "ES", "cities": ["Madrid", "Barcelona", "Valencia", "Seville", "Bilbao"], "weight": 5},
    {"country": "IT", "cities": ["Rome", "Milan", "Naples", "Turin", "Palermo"], "weight": 4},
]

WEIGHTED_GEO = []
for geo in GEO_DISTRIBUTION:
    WEIGHTED_GEO.extend([geo] * geo["weight"])


# =============================================================================
# SPECIAL EVENTS & ANOMALIES
# =============================================================================
SPECIAL_EVENTS = {
    # Major sales events (day of year -> event info)
    # Black Friday (late November)
    "black_friday": {"month": 11, "day": 29, "traffic_multiplier": 8.0, "duration_days": 4},
    # Cyber Monday
    "cyber_monday": {"month": 12, "day": 2, "traffic_multiplier": 6.0, "duration_days": 1},
    # Christmas shopping
    "christmas_rush": {"month": 12, "day_start": 15, "day_end": 24, "traffic_multiplier": 3.5},
    # New Year sales
    "new_year_sale": {"month": 1, "day_start": 1, "day_end": 7, "traffic_multiplier": 2.5},
    # Valentine's Day
    "valentines": {"month": 2, "day_start": 10, "day_end": 14, "traffic_multiplier": 2.0},
    # Prime Day / Summer Sale (mid-July)
    "summer_sale": {"month": 7, "day_start": 12, "day_end": 15, "traffic_multiplier": 4.0},
}

KNOWN_ANOMALY_PATTERNS = [
    # Database outage - every 2nd month, 15th day, around 2-4 AM
    {"type": "db_outage", "day": 15, "hour_start": 2, "hour_end": 4, "error_rate": 0.8, "months": [2, 4, 6, 8, 10, 12]},
    # Deployment issues - every month, random Wednesday evening
    {"type": "deployment", "weekday": 2, "hour_start": 18, "hour_end": 20, "error_rate": 0.4},
    # Payment gateway issues - occasional
    {"type": "payment_failure", "probability": 0.001, "error_rate": 0.6, "endpoints": ["checkout_payment", "order_confirm"]},
    # Traffic spike causing slowdowns - random
    {"type": "traffic_spike", "probability": 0.002, "latency_multiplier": 5.0},
]


# =============================================================================
# SMART DATA GENERATION
# =============================================================================
@dataclass
class UserSession:
    """Represents a user session with shopping behavior."""
    session_id: str
    user_id: Optional[str]
    device_type: str
    user_agent: str
    geo: Dict
    start_time: datetime
    intent: UserIntent
    cart_items: List[Dict] = field(default_factory=list)
    viewed_products: List[str] = field(default_factory=list)
    
    @classmethod
    def create_random(cls, timestamp: datetime) -> 'UserSession':
        """Create a random user session."""
        device_type = random.choices(
            ["mobile", "desktop", "bot"],
            weights=[55, 40, 5]
        )[0]
        
        geo = random.choice(WEIGHTED_GEO)
        
        # 30% of users are logged in
        user_id = f"user_{random.randint(1, 50000)}" if random.random() < 0.30 else None
        
        intent = random.choices(
            list(UserIntent),
            weights=[40, 25, 10, 15, 8, 2]  # Most users just browse
        )[0]
        
        return cls(
            session_id=hashlib.md5(f"{timestamp.isoformat()}{random.random()}".encode()).hexdigest()[:16],
            user_id=user_id,
            device_type=device_type,
            user_agent=random.choice(USER_AGENTS[device_type]),
            geo={"country": geo["country"], "city": random.choice(geo["cities"])},
            start_time=timestamp,
            intent=intent,
        )


def get_status_code(is_anomaly: bool) -> int:
    """Get a status code based on normal or anomaly conditions."""
    if is_anomaly:
        return random.choice(STATUS_CODES_ANOMALY)
    
    # Weighted random selection
    codes = []
    for code, weight in STATUS_CODES_NORMAL.items():
        codes.extend([code] * int(weight * 10))
    return random.choice(codes)


def get_response_time(status_code: int, endpoint_name: str, is_anomaly: bool) -> int:
    """Get realistic response time in milliseconds."""
    base_times = {
        "homepage": (50, 200),
        "product_list": (100, 400),
        "product_detail": (80, 250),
        "search": (150, 500),
        "cart_view": (50, 150),
        "cart_add": (100, 300),
        "checkout_payment": (500, 2000),
        "order_confirm": (200, 800),
    }
    
    # Get base range
    base_min, base_max = base_times.get(endpoint_name, (50, 300))
    
    if is_anomaly:
        # Anomalous: very slow
        return random.randint(3000, 30000)
    elif status_code >= 500:
        return random.randint(1000, 5000)
    elif status_code >= 400:
        return random.randint(20, 100)  # Fast error responses
    else:
        return random.randint(base_min, base_max)


def get_traffic_multiplier(dt: datetime) -> float:
    """
    Calculate traffic multiplier based on:
    - Time of day (business hours vs night)
    - Day of week (weekday vs weekend)
    - Month (seasonal patterns)
    - Special events (Black Friday, etc.)
    """
    hour = dt.hour
    weekday = dt.weekday()  # 0=Monday, 6=Sunday
    month = dt.month
    day = dt.day
    
    multiplier = 1.0
    
    # === Time of Day Pattern ===
    if weekday < 5:  # Weekday
        if 0 <= hour < 6:
            multiplier *= 0.15  # Night: very low
        elif 6 <= hour < 9:
            multiplier *= 0.5   # Morning ramp-up
        elif 9 <= hour < 12:
            multiplier *= 1.0   # Late morning peak
        elif 12 <= hour < 14:
            multiplier *= 1.3   # Lunch break shopping!
        elif 14 <= hour < 17:
            multiplier *= 0.9   # Afternoon
        elif 17 <= hour < 21:
            multiplier *= 1.5   # Evening peak (after work)
        elif 21 <= hour < 23:
            multiplier *= 1.0   # Late evening
        else:
            multiplier *= 0.4   # Late night
    else:  # Weekend
        if 0 <= hour < 8:
            multiplier *= 0.2
        elif 8 <= hour < 11:
            multiplier *= 0.6
        elif 11 <= hour < 14:
            multiplier *= 1.2   # Weekend brunch browsing
        elif 14 <= hour < 18:
            multiplier *= 1.0
        elif 18 <= hour < 22:
            multiplier *= 1.3   # Weekend evening shopping
        else:
            multiplier *= 0.5
    
    # === Weekend adjustment ===
    if weekday >= 5:
        multiplier *= 0.85  # Slightly less overall on weekends
    
    # === Monthly/Seasonal Pattern ===
    seasonal_factors = {
        1: 0.9,   # January (post-holiday slump)
        2: 0.85,  # February (slow)
        3: 0.9,   # March
        4: 0.95,  # April
        5: 1.0,   # May
        6: 0.95,  # June
        7: 0.9,   # July
        8: 0.95,  # August (back to school starting)
        9: 1.1,   # September
        10: 1.2,  # October (pre-holiday buildup)
        11: 1.5,  # November (holiday shopping)
        12: 1.8,  # December (peak season)
    }
    multiplier *= seasonal_factors.get(month, 1.0)
    
    # === Special Events ===
    # Black Friday weekend
    if month == 11 and 27 <= day <= 30:
        days_from_bf = abs(day - 29)
        bf_multiplier = 8.0 - (days_from_bf * 1.5)
        multiplier *= max(1.0, bf_multiplier)
    
    # Cyber Monday
    if month == 12 and day == 2:
        multiplier *= 6.0
    
    # Christmas rush
    if month == 12 and 15 <= day <= 23:
        multiplier *= 3.0
    
    # Christmas Eve/Day drop
    if month == 12 and day in [24, 25]:
        multiplier *= 0.3
    
    # New Year sale
    if month == 1 and 1 <= day <= 5:
        multiplier *= 2.0
    
    # Valentine's Day
    if month == 2 and 10 <= day <= 14:
        multiplier *= 1.8
    
    # Prime Day / Summer Sale
    if month == 7 and 12 <= day <= 15:
        multiplier *= 4.0
    
    return multiplier


def should_inject_anomaly(dt: datetime, endpoint_name: str) -> Tuple[bool, str]:
    """
    Determine if this request should be anomalous.
    Returns (is_anomaly, anomaly_type).
    """
    hour = dt.hour
    day = dt.day
    month = dt.month
    weekday = dt.weekday()
    
    # Database outage pattern
    if day == 15 and month in [2, 4, 6, 8, 10, 12] and 2 <= hour <= 4:
        if random.random() < 0.5:
            return True, "db_outage"
    
    # Deployment issues (Wednesday evenings)
    if weekday == 2 and 18 <= hour <= 20:
        if random.random() < 0.1:
            return True, "deployment"
    
    # Payment gateway issues
    if endpoint_name in ["checkout_payment", "order_confirm"]:
        if random.random() < 0.008:
            return True, "payment_failure"
    
    # Random traffic spike causing timeouts
    if random.random() < 0.002:
        return True, "traffic_spike"
    
    # Random baseline anomaly
    if random.random() < HISTORICAL_ANOMALY_RATE:
        return True, "random"
    
    return False, ""


def generate_log_entry(
    timestamp: datetime,
    session: Optional[UserSession] = None,
    is_anomaly: bool = False,
    anomaly_type: str = ""
) -> dict:
    """Generate a single e-commerce log entry."""
    
    # Select endpoint
    endpoint_name, endpoint_data = random.choice(WEIGHTED_ENDPOINTS)
    path = endpoint_data["path"]
    method = endpoint_data["method"]
    
    # Select product if needed
    category, product = random.choice(WEIGHTED_PRODUCTS)
    
    # Fill in path parameters
    if "{product_id}" in path:
        path = path.replace("{product_id}", product["id"])
    if "{category}" in path:
        path = path.replace("{category}", category)
    if "{item_id}" in path:
        path = path.replace("{item_id}", str(random.randint(1, 100000)))
    if "{order_id}" in path:
        path = path.replace("{order_id}", f"ORD-{random.randint(100000, 999999)}")
    
    # Generate session if not provided
    if session is None:
        session = UserSession.create_random(timestamp)
    
    # Determine status and response time
    status_code = get_status_code(is_anomaly)
    response_time = get_response_time(status_code, endpoint_name, is_anomaly)
    
    # Calculate bytes
    if status_code >= 400:
        bytes_sent = random.randint(100, 1000)
    elif endpoint_name in ["product_list", "search"]:
        bytes_sent = random.randint(10000, 100000)
    elif endpoint_name in ["product_detail"]:
        bytes_sent = random.randint(5000, 30000)
    else:
        bytes_sent = random.randint(500, 15000)
    
    # Build log entry
    entry = {
        "@timestamp": timestamp.isoformat().replace("+00:00", "Z") if timestamp.tzinfo else timestamp.isoformat() + "Z",
        
        # Request info
        "method": method,
        "endpoint": path,
        "endpoint_name": endpoint_name,
        "status_code": status_code,
        "response_time_ms": response_time,
        "bytes_sent": bytes_sent,
        
        # Session & User
        "session_id": session.session_id,
        "user_id": session.user_id,
        "is_authenticated": session.user_id is not None,
        
        # Device & Client
        "device_type": session.device_type,
        "client_ip": fake.ipv4_public(),
        "user_agent": session.user_agent,
        
        # Geographic
        "geo": session.geo,
        
        # E-commerce context
        "category": category if "{product_id}" in endpoint_data["path"] or "{category}" in endpoint_data["path"] else None,
        "product_id": product["id"] if "{product_id}" in endpoint_data["path"] else None,
        "product_name": product["name"] if "{product_id}" in endpoint_data["path"] else None,
        "product_price": product["price"] if "{product_id}" in endpoint_data["path"] else None,
        
        # Request metadata
        "request_id": fake.uuid4(),
        
        # Anomaly markers (for validation, not used in detection)
        "is_anomaly_marker": is_anomaly,
        "anomaly_type": anomaly_type if is_anomaly else None,
    }
    
    # Add payment info for checkout endpoints
    if endpoint_name in ["checkout_payment", "order_confirm"]:
        entry["payment_method"] = random.choice(PAYMENT_METHODS)
        if endpoint_name == "order_confirm" and status_code < 400:
            entry["order_total"] = round(random.uniform(20, 500), 2)
            entry["items_count"] = random.randint(1, 8)
    
    # Add search query for search endpoints
    if endpoint_name in ["search", "search_suggestions"]:
        search_terms = [
            product["name"].split()[0] for _, product in random.sample(WEIGHTED_PRODUCTS, min(5, len(WEIGHTED_PRODUCTS)))
        ]
        entry["search_query"] = random.choice(search_terms).lower()
        entry["search_results_count"] = random.randint(0, 150) if status_code == 200 else 0
    
    return entry


# =============================================================================
# ELASTICSEARCH OPERATIONS - DIRECT HTTP API (bypasses elasticsearch-py)
# =============================================================================
class ElasticsearchManager:
    """Direct HTTP client for Elasticsearch - bypasses elasticsearch-py overhead."""
    
    def __init__(self, host: str, index_name: str):
        self.host = host.rstrip('/')
        self.index_name = index_name
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def connect_async(self, max_retries: int = 30, retry_delay: int = 5) -> bool:
        """Connect to Elasticsearch with retries using aiohttp."""
        connector = aiohttp.TCPConnector(
            limit=200,           # Total connection pool size
            limit_per_host=100,  # Per-host connections (match bulk threads)
            ttl_dns_cache=300,   # DNS cache
            keepalive_timeout=120,
            enable_cleanup_closed=True,
        )
        timeout = aiohttp.ClientTimeout(total=300, connect=30)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={"Content-Type": "application/x-ndjson"},
        )
        
        for attempt in range(max_retries):
            try:
                async with self.session.get(f"{self.host}/") as resp:
                    if resp.status == 200:
                        info = await resp.json()
                        logger.info(f"Connected to Elasticsearch at {self.host} (version: {info['version']['number']})")
                        return True
            except Exception as e:
                logger.warning(f"Connection attempt {attempt + 1}/{max_retries} failed: {e}")
            await asyncio.sleep(retry_delay)
        
        logger.error("Failed to connect to Elasticsearch")
        return False
    
    def connect(self, max_retries: int = 30, retry_delay: int = 5) -> bool:
        """Sync wrapper for connect."""
        return asyncio.get_event_loop().run_until_complete(
            self.connect_async(max_retries, retry_delay)
        )
    
    async def create_index_async(self) -> bool:
        """Create the e-commerce logs index with optimized bulk loading settings."""
        mapping = {
            "settings": {
                "number_of_shards": 2,
                "number_of_replicas": 0,
                "refresh_interval": "-1",
                "index.mapping.total_fields.limit": 500,
                "index.translog.durability": "async",
                "index.translog.sync_interval": "30s",
            },
            "mappings": {
                "properties": {
                    "@timestamp": {"type": "date"},
                    "method": {"type": "keyword"},
                    "endpoint": {"type": "keyword"},
                    "endpoint_name": {"type": "keyword"},
                    "status_code": {"type": "integer"},
                    "response_time_ms": {"type": "integer"},
                    "bytes_sent": {"type": "long"},
                    "session_id": {"type": "keyword"},
                    "user_id": {"type": "keyword"},
                    "is_authenticated": {"type": "boolean"},
                    "device_type": {"type": "keyword"},
                    "client_ip": {"type": "ip"},
                    "user_agent": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                    "geo": {"properties": {"country": {"type": "keyword"}, "city": {"type": "keyword"}}},
                    "category": {"type": "keyword"},
                    "product_id": {"type": "keyword"},
                    "product_name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                    "product_price": {"type": "float"},
                    "search_query": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                    "search_results_count": {"type": "integer"},
                    "payment_method": {"type": "keyword"},
                    "order_total": {"type": "float"},
                    "items_count": {"type": "integer"},
                    "request_id": {"type": "keyword"},
                    "is_anomaly_marker": {"type": "boolean"},
                    "anomaly_type": {"type": "keyword"},
                }
            }
        }
        
        try:
            # Check if exists
            async with self.session.head(f"{self.host}/{self.index_name}") as resp:
                if resp.status == 200:
                    logger.info(f"Index {self.index_name} exists, deleting...")
                    async with self.session.delete(f"{self.host}/{self.index_name}") as del_resp:
                        await del_resp.read()
            
            # Create index
            async with self.session.put(
                f"{self.host}/{self.index_name}",
                data=fast_json_dumps(mapping),
                headers={"Content-Type": "application/json"}
            ) as resp:
                if resp.status in (200, 201):
                    logger.info(f"Created index: {self.index_name} (refresh DISABLED for bulk load)")
                    return True
                else:
                    error = await resp.text()
                    logger.error(f"Failed to create index: {error}")
                    return False
        except Exception as e:
            logger.error(f"Failed to create index: {e}")
            return False
    
    def create_index(self) -> bool:
        """Sync wrapper."""
        return asyncio.get_event_loop().run_until_complete(self.create_index_async())
    
    async def bulk_index_async(self, documents: List[dict]) -> Tuple[int, int]:
        """
        Direct bulk API call - bypasses elasticsearch-py entirely.
        Returns (success_count, error_count).
        """
        if not documents:
            return 0, 0
        
        # Build NDJSON bulk body directly with orjson
        lines = []
        action_line = fast_json_dumps({"index": {"_index": self.index_name}})
        for doc in documents:
            lines.append(action_line)
            lines.append(fast_json_dumps(doc))
        
        body = b'\n'.join(lines) + b'\n'
        
        try:
            async with self.session.post(
                f"{self.host}/_bulk",
                data=body,
                headers={"Content-Type": "application/x-ndjson"},
                compress=True,  # Enable gzip compression
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    errors = sum(1 for item in result.get("items", []) if item.get("index", {}).get("error"))
                    return len(documents) - errors, errors
                else:
                    return 0, len(documents)
        except Exception as e:
            logger.error(f"Bulk request failed: {e}")
            return 0, len(documents)
    
    async def restore_settings_async(self):
        """Restore normal index settings."""
        try:
            settings = {"index": {"refresh_interval": "5s", "translog.durability": "request"}}
            async with self.session.put(
                f"{self.host}/{self.index_name}/_settings",
                data=fast_json_dumps(settings),
                headers={"Content-Type": "application/json"}
            ) as resp:
                if resp.status == 200:
                    logger.info(f"Restored normal settings for {self.index_name}")
        except Exception as e:
            logger.warning(f"Failed to restore settings: {e}")
    
    async def refresh_async(self):
        """Refresh the index."""
        try:
            async with self.session.post(f"{self.host}/{self.index_name}/_refresh") as resp:
                await resp.read()
        except Exception as e:
            logger.warning(f"Refresh failed: {e}")
    
    async def close(self):
        """Close the session."""
        if self.session:
            await self.session.close()


# =============================================================================
# PHASE 1: HISTORICAL DATA GENERATION (MASSIVE VOLUME - OPTIMIZED)
# =============================================================================

def generate_day_logs(args: Tuple) -> Tuple[List[dict], int]:
    """
    Generate all logs for a single day - designed for parallel execution.
    Returns (list_of_log_entries, anomaly_count)
    """
    day_offset, base_date, base_requests_per_hour, anomaly_rate = args
    
    # Re-seed random for this process
    random.seed(day_offset * 1000 + int(time.time()) % 10000)
    
    # Create a local Faker instance
    local_fake = Faker()
    local_fake.seed_instance(day_offset)
    
    current_date = base_date + timedelta(days=day_offset)
    entries = []
    anomaly_count = 0
    
    for hour in range(24):
        hour_start = current_date.replace(hour=hour, minute=0, second=0, microsecond=0)
        
        # Calculate traffic volume
        multiplier = get_traffic_multiplier(hour_start)
        num_requests = int(base_requests_per_hour * multiplier)
        num_requests = random.randint(int(num_requests * 0.85), int(num_requests * 1.15))
        
        # Pre-generate all timestamps for this hour
        for _ in range(num_requests):
            minute = random.randint(0, 59)
            second = random.randint(0, 59)
            microsecond = random.randint(0, 999999)
            
            timestamp = hour_start.replace(
                minute=minute, second=second, microsecond=microsecond
            )
            
            endpoint_name, _ = random.choice(WEIGHTED_ENDPOINTS)
            is_anomaly, anomaly_type = should_inject_anomaly(timestamp, endpoint_name)
            if is_anomaly:
                anomaly_count += 1
            
            # Generate entry using fast path
            entry = generate_log_entry_fast(timestamp, is_anomaly, anomaly_type, local_fake)
            entries.append(entry)
    
    return entries, anomaly_count


def generate_log_entry_fast(timestamp: datetime, is_anomaly: bool, anomaly_type: str, local_fake: Faker) -> dict:
    """
    Fast log entry generation without UserSession object overhead.
    """
    # Select endpoint
    endpoint_name, endpoint_data = random.choice(WEIGHTED_ENDPOINTS)
    path = endpoint_data["path"]
    method = endpoint_data["method"]
    
    # Select product
    category, product = random.choice(WEIGHTED_PRODUCTS)
    
    # Fill path parameters
    if "{product_id}" in path:
        path = path.replace("{product_id}", product["id"])
    if "{category}" in path:
        path = path.replace("{category}", category)
    if "{item_id}" in path:
        path = path.replace("{item_id}", str(random.randint(1, 100000)))
    if "{order_id}" in path:
        path = path.replace("{order_id}", f"ORD-{random.randint(100000, 999999)}")
    
    # Device type
    device_type = random.choices(["mobile", "desktop", "bot"], weights=[55, 40, 5])[0]
    
    # Geo
    geo = random.choice(WEIGHTED_GEO)
    
    # Status and response time
    status_code = get_status_code(is_anomaly)
    response_time = get_response_time(status_code, endpoint_name, is_anomaly)
    
    # Bytes
    if status_code >= 400:
        bytes_sent = random.randint(100, 1000)
    elif endpoint_name in ["product_list", "search"]:
        bytes_sent = random.randint(10000, 100000)
    elif endpoint_name in ["product_detail"]:
        bytes_sent = random.randint(5000, 30000)
    else:
        bytes_sent = random.randint(500, 15000)
    
    # User
    user_id = f"user_{random.randint(1, 50000)}" if random.random() < 0.30 else None
    
    entry = {
        "@timestamp": timestamp.isoformat().replace("+00:00", "Z") if timestamp.tzinfo else timestamp.isoformat() + "Z",
        "method": method,
        "endpoint": path,
        "endpoint_name": endpoint_name,
        "status_code": status_code,
        "response_time_ms": response_time,
        "bytes_sent": bytes_sent,
        "session_id": hashlib.md5(f"{timestamp.isoformat()}{random.random()}".encode()).hexdigest()[:16],
        "user_id": user_id,
        "is_authenticated": user_id is not None,
        "device_type": device_type,
        "client_ip": local_fake.ipv4_public(),
        "user_agent": random.choice(USER_AGENTS[device_type]),
        "geo": {"country": geo["country"], "city": random.choice(geo["cities"])},
        "category": category if "{product_id}" in endpoint_data["path"] or "{category}" in endpoint_data["path"] else None,
        "product_id": product["id"] if "{product_id}" in endpoint_data["path"] else None,
        "product_name": product["name"] if "{product_id}" in endpoint_data["path"] else None,
        "product_price": product["price"] if "{product_id}" in endpoint_data["path"] else None,
        "request_id": local_fake.uuid4(),
        "is_anomaly_marker": is_anomaly,
        "anomaly_type": anomaly_type if is_anomaly else None,
    }
    
    # Payment info
    if endpoint_name in ["checkout_payment", "order_confirm"]:
        entry["payment_method"] = random.choice(PAYMENT_METHODS)
        if endpoint_name == "order_confirm" and status_code < 400:
            entry["order_total"] = round(random.uniform(20, 500), 2)
            entry["items_count"] = random.randint(1, 8)
    
    # Search info
    if endpoint_name in ["search", "search_suggestions"]:
        search_terms = [p["name"].split()[0] for _, p in random.sample(WEIGHTED_PRODUCTS, min(5, len(WEIGHTED_PRODUCTS)))]
        entry["search_query"] = random.choice(search_terms).lower()
        entry["search_results_count"] = random.randint(0, 150) if status_code == 200 else 0
    
    return entry


def streaming_bulk_actions(es_manager: ElasticsearchManager, days: int, start_date: datetime) -> Generator:
    """
    Generator that yields bulk actions for streaming bulk indexing.
    This allows continuous streaming without holding all data in memory.
    """
    for day_offset in range(days):
        current_date = start_date + timedelta(days=day_offset)
        
        for hour in range(24):
            hour_start = current_date.replace(hour=hour, minute=0, second=0, microsecond=0)
            
            multiplier = get_traffic_multiplier(hour_start)
            num_requests = int(BASE_REQUESTS_PER_HOUR * multiplier)
            num_requests = random.randint(int(num_requests * 0.85), int(num_requests * 1.15))
            
            for _ in range(num_requests):
                minute = random.randint(0, 59)
                second = random.randint(0, 59)
                microsecond = random.randint(0, 999999)
                
                timestamp = hour_start.replace(
                    minute=minute, second=second, microsecond=microsecond
                )
                
                endpoint_name, _ = random.choice(WEIGHTED_ENDPOINTS)
                is_anomaly, anomaly_type = should_inject_anomaly(timestamp, endpoint_name)
                
                entry = generate_log_entry_fast(timestamp, is_anomaly, anomaly_type, fake)
                
                yield {
                    "_index": es_manager.index_name,
                    "_source": entry
                }


# =============================================================================
# STREAMING BULK INDEXING - CONTINUOUS DATA FLOW
# =============================================================================
def generate_day_batch(args) -> List[dict]:
    """
    Worker function to generate all logs for a single day.
    Runs in separate process for CPU parallelism.
    """
    day_offset, days_total, start_date, index_name, base_requests = args
    
    # Each process needs its own Faker instance
    local_fake = Faker()
    local_fake.seed_instance(day_offset)  # Reproducible but different per day
    
    current_date = start_date + timedelta(days=day_offset)
    batch = []
    
    for hour in range(24):
        hour_start = current_date.replace(hour=hour, minute=0, second=0, microsecond=0)
        
        multiplier = get_traffic_multiplier(hour_start)
        num_requests = int(base_requests * multiplier)
        num_requests = random.randint(int(num_requests * 0.85), int(num_requests * 1.15))
        
        for _ in range(num_requests):
            minute = random.randint(0, 59)
            second = random.randint(0, 59)
            microsecond = random.randint(0, 999999)
            
            timestamp = hour_start.replace(
                minute=minute, second=second, microsecond=microsecond
            )
            
            endpoint_name, _ = random.choice(WEIGHTED_ENDPOINTS)
            is_anomaly, anomaly_type = should_inject_anomaly(timestamp, endpoint_name)
            
            entry = generate_log_entry_fast(timestamp, is_anomaly, anomaly_type, local_fake)
            batch.append(entry)
    
    return batch


async def stream_bulk_index(session: aiohttp.ClientSession, host: str, index_name: str,
                            documents: List[dict], max_retries: int = 3) -> Tuple[int, int]:
    """
    Stream documents to ES using async generator (chunked transfer).
    Includes retry logic with exponential backoff.
    Returns (success_count, error_count).
    """
    if not documents:
        return 0, 0
    
    for attempt in range(max_retries):
        try:
            # Async generator for streaming body
            async def body_generator():
                action_line = fast_json_dumps({"index": {"_index": index_name}})
                for doc in documents:
                    yield action_line + b'\n'
                    yield fast_json_dumps(doc) + b'\n'
            
            async with session.post(
                f"{host}/_bulk",
                data=body_generator(),
                headers={"Content-Type": "application/x-ndjson"},
                timeout=aiohttp.ClientTimeout(total=120),  # 2 min timeout
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    errors = sum(1 for item in result.get("items", []) if item.get("index", {}).get("error"))
                    return len(documents) - errors, errors
                elif resp.status == 429:  # Too many requests - backoff and retry
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    return 0, len(documents)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                await asyncio.sleep(wait_time)
                continue
            else:
                logger.warning(f"Stream bulk failed after {max_retries} attempts: {e}")
                return 0, len(documents)
        except Exception as e:
            logger.error(f"Stream bulk unexpected error: {e}")
            return 0, len(documents)
    
    return 0, len(documents)


async def generate_historical_data_async(es_manager: ElasticsearchManager, days: int = 365) -> int:
    """
    STREAMING historical data generation using:
    - ProcessPoolExecutor for parallel CPU-bound document generation
    - Async generators for chunked transfer encoding to ES
    - PIPELINE: stream each day as it completes (no batching waves)
    """
    logger.info("=" * 70)
    logger.info("PHASE 1: STREAMING HISTORICAL E-COMMERCE DATA GENERATION")
    logger.info("=" * 70)
    
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    
    estimated_total = int(days * 24 * BASE_REQUESTS_PER_HOUR * 1.5)
    num_workers = min(NUM_WORKERS, mp.cpu_count())
    
    logger.info(f"Date range: {start_date.date()} to {end_date.date()}")
    logger.info(f"Index: {es_manager.index_name}")
    logger.info(f"Base requests/hour: {BASE_REQUESTS_PER_HOUR:,}")
    logger.info(f"Estimated total: ~{estimated_total:,} documents")
    logger.info(f"Mode: STREAMING PIPELINE (continuous flow)")
    logger.info(f"orjson: {'ENABLED' if ORJSON_ENABLED else 'disabled'}")
    logger.info(f"uvloop: {'ENABLED' if UVLOOP_ENABLED else 'disabled'}")
    logger.info(f"Generator workers: {num_workers} | Concurrent streams: {BULK_THREAD_COUNT} | Chunk: {CHUNK_SIZE}")
    
    start_time = time.time()
    total_docs = 0
    total_errors = 0
    
    # Prepare generation args for all days
    gen_args = [
        (day_offset, days, start_date, es_manager.index_name, BASE_REQUESTS_PER_HOUR)
        for day_offset in range(days)
    ]
    
    logger.info("Starting STREAMING PIPELINE generation and indexing...")
    
    last_report_time = start_time
    report_interval = 15
    
    # Semaphore for concurrent streams
    semaphore = asyncio.Semaphore(BULK_THREAD_COUNT)
    
    async def stream_with_semaphore(docs):
        async with semaphore:
            return await stream_bulk_index(es_manager.session, es_manager.host, es_manager.index_name, docs)
    
    # MEMORY-SAFE pipeline with limited concurrency
    # Don't submit ALL days at once - limit to prevent memory explosion
    loop = asyncio.get_event_loop()
    pending_streams = set()
    pending_generators = set()
    max_pending_streams = BULK_THREAD_COUNT  # How many bulk streams can be in flight
    max_pending_generators = NUM_WORKERS + 2  # Limit days generating in parallel
    
    gen_args_iter = iter(enumerate(gen_args))
    days_submitted = 0
    days_completed = 0
    total_days = len(gen_args)
    
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        # Initial batch of day generators
        for _ in range(min(max_pending_generators, total_days)):
            try:
                i, args = next(gen_args_iter)
                future = loop.run_in_executor(executor, generate_day_batch, args)
                pending_generators.add((future, i))
                days_submitted += 1
            except StopIteration:
                break
        
        # Process days as they complete, submitting new ones to keep pipeline full
        while pending_generators or pending_streams:
            # Wait for something to complete (generator or stream)
            all_pending = {f for f, i in pending_generators} | pending_streams
            if not all_pending:
                break
                
            done, _ = await asyncio.wait(all_pending, return_when=asyncio.FIRST_COMPLETED)
            
            for completed in done:
                # Check if it's a generator (day) that completed
                gen_match = None
                for gen_future, gen_idx in list(pending_generators):
                    if gen_future == completed:
                        gen_match = (gen_future, gen_idx)
                        break
                
                if gen_match:
                    pending_generators.discard(gen_match)
                    days_completed += 1
                    try:
                        day_docs = completed.result()
                        # Split into chunks and stream immediately
                        for i in range(0, len(day_docs), CHUNK_SIZE):
                            chunk = day_docs[i:i + CHUNK_SIZE]
                            stream_task = asyncio.create_task(stream_with_semaphore(chunk))
                            pending_streams.add(stream_task)
                    except Exception as e:
                        logger.warning(f"Generator error: {e}")
                    
                    # Submit next day if any left AND we have room
                    if len(pending_generators) < max_pending_generators:
                        try:
                            idx, args = next(gen_args_iter)
                            future = loop.run_in_executor(executor, generate_day_batch, args)
                            pending_generators.add((future, idx))
                            days_submitted += 1
                        except StopIteration:
                            pass
                else:
                    # It's a stream that completed
                    pending_streams.discard(completed)
                    try:
                        result = completed.result()
                        if isinstance(result, tuple):
                            total_docs += result[0]
                            total_errors += result[1]
                    except Exception as e:
                        logger.warning(f"Stream error: {e}")
            
            # BACKPRESSURE: If too many pending streams, wait before submitting more generators
            while len(pending_streams) > max_pending_streams:
                done_s, pending_streams = await asyncio.wait(
                    pending_streams,
                    return_when=asyncio.FIRST_COMPLETED
                )
                for stream in done_s:
                    try:
                        result = stream.result()
                        if isinstance(result, tuple):
                            total_docs += result[0]
                            total_errors += result[1]
                    except Exception as e:
                        logger.warning(f"Stream error: {e}")
            
            # Progress report
            now = time.time()
            if now - last_report_time >= report_interval:
                elapsed = now - start_time
                rate = total_docs / elapsed if elapsed > 0 else 0
                pct = (total_docs / estimated_total) * 100
                eta = (estimated_total - total_docs) / rate if rate > 0 else 0
                pending = len(pending_streams)
                
                logger.info(
                    f"Progress: {pct:.1f}% | "
                    f"{total_docs:,} docs | "
                    f"{rate:,.0f} docs/sec | "
                    f"ETA: {eta/60:.1f} min | "
                    f"pending: {pending}"
                )
                last_report_time = now
        
        # Wait for remaining streams
        if pending_streams:
            results = await asyncio.gather(*pending_streams, return_exceptions=True)
            for result in results:
                if isinstance(result, tuple):
                    total_docs += result[0]
                    total_errors += result[1]
    
    # Restore settings and refresh
    logger.info("Restoring index settings and refreshing...")
    await es_manager.restore_settings_async()
    await es_manager.refresh_async()
    
    elapsed = time.time() - start_time
    logger.info("=" * 70)
    logger.info("HISTORICAL DATA GENERATION COMPLETE!")
    logger.info(f"Total documents: {total_docs:,}")
    logger.info(f"Errors: {total_errors:,}")
    logger.info(f"Time elapsed: {elapsed/60:.1f} minutes")
    logger.info(f"Average rate: {total_docs/elapsed:,.0f} docs/sec")
    logger.info("=" * 70)
    
    return total_docs


def generate_historical_data_fast(es_manager: ElasticsearchManager, days: int = 365) -> int:
    """Sync wrapper for async generation."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(generate_historical_data_async(es_manager, days))
    finally:
        loop.close()
    
    # Restore settings and refresh
    logger.info("Restoring index settings and refreshing...")
    es_manager.restore_normal_settings()
    es_manager.refresh()
    
    elapsed = time.time() - start_time
    logger.info("=" * 70)
    logger.info("HISTORICAL DATA GENERATION COMPLETE!")
    logger.info(f"Total documents: {total_docs:,}")
    logger.info(f"Errors: {total_errors:,}")
    logger.info(f"Time elapsed: {elapsed/60:.1f} minutes")
    logger.info(f"Average rate: {total_docs/elapsed:,.0f} docs/sec")
    logger.info("=" * 70)
    
    return total_docs


def generate_historical_data(es_manager: ElasticsearchManager, days: int = 365) -> int:
    """Generate massive historical data - delegates to fast version."""
    return generate_historical_data_fast(es_manager, days)


# =============================================================================
# PHASE 2: CONTINUOUS LOG GENERATION
# =============================================================================
class ContinuousGenerator:
    def __init__(self, es_manager: ElasticsearchManager):
        self.es_manager = es_manager
        self.running = True
        self.total_logs = 0
        self.total_anomalies = 0
        self.start_time = None
        
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        logger.info("Shutdown signal received, stopping...")
        self.running = False
    
    def run(self):
        """Run continuous log generation."""
        logger.info("=" * 70)
        logger.info("PHASE 2: STARTING CONTINUOUS E-COMMERCE LOG GENERATION")
        logger.info("=" * 70)
        logger.info(f"Interval: {CONTINUOUS_INTERVAL}s")
        logger.info(f"Logs per interval: {LOGS_PER_INTERVAL_MIN}-{LOGS_PER_INTERVAL_MAX}")
        logger.info(f"Burst probability: {BURST_PROBABILITY*100:.1f}%")
        
        self.start_time = time.time()
        last_stats_time = time.time()
        
        while self.running:
            try:
                now = datetime.now(timezone.utc)
                batch = []
                
                # Get current traffic multiplier
                multiplier = get_traffic_multiplier(now)
                base_logs = random.randint(LOGS_PER_INTERVAL_MIN, LOGS_PER_INTERVAL_MAX)
                num_logs = int(base_logs * multiplier)
                
                # Check for traffic burst (flash sale, viral moment)
                if random.random() < BURST_PROBABILITY:
                    burst_size = random.randint(BURST_SIZE_MIN, BURST_SIZE_MAX)
                    logger.info(f"🔥 Traffic burst! +{burst_size} requests")
                    num_logs += burst_size
                
                # Generate logs
                for _ in range(num_logs):
                    ts_offset = random.uniform(0, CONTINUOUS_INTERVAL)
                    timestamp = now - timedelta(seconds=ts_offset)
                    
                    session = UserSession.create_random(timestamp)
                    endpoint_name, _ = random.choice(WEIGHTED_ENDPOINTS)
                    is_anomaly, anomaly_type = should_inject_anomaly(timestamp, endpoint_name)
                    
                    if is_anomaly:
                        self.total_anomalies += 1
                    
                    batch.append(generate_log_entry(timestamp, session, is_anomaly, anomaly_type))
                
                # Index batch
                indexed = self.es_manager.bulk_index(batch)
                self.total_logs += indexed
                
                # Print stats every 60 seconds
                if time.time() - last_stats_time >= 60:
                    self._print_stats()
                    last_stats_time = time.time()
                
                time.sleep(CONTINUOUS_INTERVAL)
                
            except Exception as e:
                logger.error(f"Error in continuous generation: {e}")
                time.sleep(5)
        
        self._print_stats()
        logger.info("Continuous generation stopped")
    
    def _print_stats(self):
        elapsed = time.time() - self.start_time
        rate = self.total_logs / elapsed if elapsed > 0 else 0
        anomaly_pct = 100 * self.total_anomalies / max(1, self.total_logs)
        
        logger.info(
            f"📊 Stats: {self.total_logs:,} logs | "
            f"{self.total_anomalies:,} anomalies ({anomaly_pct:.2f}%) | "
            f"Rate: {rate:.1f} logs/sec"
        )


async def run_continuous_async(es_manager: ElasticsearchManager):
    """
    Async continuous log generation - runs forever generating real-time logs.
    """
    logger.info("=" * 70)
    logger.info("PHASE 2: STARTING CONTINUOUS E-COMMERCE LOG GENERATION")
    logger.info("=" * 70)
    logger.info(f"Interval: {CONTINUOUS_INTERVAL}s")
    logger.info(f"Logs per interval: {LOGS_PER_INTERVAL_MIN}-{LOGS_PER_INTERVAL_MAX}")
    logger.info(f"Burst probability: {BURST_PROBABILITY*100:.1f}%")
    
    total_logs = 0
    total_anomalies = 0
    start_time = time.time()
    last_stats_time = start_time
    
    while True:
        try:
            now = datetime.now(timezone.utc)
            batch = []
            
            # Get current traffic multiplier
            multiplier = get_traffic_multiplier(now)
            base_logs = random.randint(LOGS_PER_INTERVAL_MIN, LOGS_PER_INTERVAL_MAX)
            num_logs = int(base_logs * multiplier)
            
            # Check for traffic burst (flash sale, viral moment)
            if random.random() < BURST_PROBABILITY:
                burst_size = random.randint(BURST_SIZE_MIN, BURST_SIZE_MAX)
                logger.info(f"🔥 Traffic burst! +{burst_size} requests")
                num_logs += burst_size
            
            # Generate logs
            for _ in range(num_logs):
                ts_offset = random.uniform(0, CONTINUOUS_INTERVAL)
                timestamp = now - timedelta(seconds=ts_offset)
                
                session = UserSession.create_random(timestamp)
                endpoint_name, _ = random.choice(WEIGHTED_ENDPOINTS)
                is_anomaly, anomaly_type = should_inject_anomaly(timestamp, endpoint_name)
                
                if is_anomaly:
                    total_anomalies += 1
                
                batch.append(generate_log_entry(timestamp, session, is_anomaly, anomaly_type))
            
            # Index batch using async streaming
            if batch:
                success, errors = await stream_bulk_index(
                    es_manager.session, es_manager.host, es_manager.index_name, batch
                )
                total_logs += success
            
            # Print stats every 60 seconds
            current_time = time.time()
            if current_time - last_stats_time >= 60:
                elapsed = current_time - start_time
                rate = total_logs / elapsed if elapsed > 0 else 0
                anomaly_pct = 100 * total_anomalies / max(1, total_logs)
                logger.info(
                    f"📊 Continuous Stats: {total_logs:,} logs | "
                    f"{total_anomalies:,} anomalies ({anomaly_pct:.2f}%) | "
                    f"Rate: {rate:.1f} logs/sec"
                )
                last_stats_time = current_time
            
            await asyncio.sleep(CONTINUOUS_INTERVAL)
            
        except asyncio.CancelledError:
            logger.info("Continuous generation cancelled")
            break
        except Exception as e:
            logger.error(f"Error in continuous generation: {e}")
            await asyncio.sleep(5)


# =============================================================================
# MAIN
# =============================================================================
async def main_async():
    try:
        logger.info("=" * 70)
        logger.info("🛒 SMART E-COMMERCE LOG GENERATOR - DIRECT API MODE")
        logger.info("    Simulating realistic online store traffic")
        logger.info("=" * 70)
        logger.info(f"Elasticsearch: {ES_HOST}")
        logger.info(f"Index: {INDEX_NAME}")
        logger.info(f"Historical days: {HISTORICAL_DAYS}")
        logger.info(f"Products: {sum(len(c['products']) for c in CATEGORIES.values())} across {len(CATEGORIES)} categories")
        
        # Connect to Elasticsearch using async
        es_manager = ElasticsearchManager(ES_HOST, INDEX_NAME)
        if not await es_manager.connect_async():
            logger.error("Failed to connect to Elasticsearch, exiting")
            sys.exit(1)
        
        # Create index
        if not await es_manager.create_index_async():
            logger.error("Failed to create index, exiting")
            sys.exit(1)
        
        # Phase 1: Generate historical data
        await generate_historical_data_async(es_manager, HISTORICAL_DAYS)
        
        logger.info("Historical data generation complete!")
        
        # Re-enable refresh for continuous mode
        try:
            async with es_manager.session.put(
                f"{es_manager.host}/{es_manager.index_name}/_settings",
                json={"index": {"refresh_interval": "1s"}}
            ) as resp:
                if resp.status == 200:
                    logger.info("Re-enabled index refresh for continuous mode")
        except Exception as e:
            logger.warning(f"Could not re-enable refresh: {e}")
        
        # Phase 2: Continuous generation (runs forever)
        await run_continuous_async(es_manager)
    except Exception as e:
        logger.error(f"FATAL ERROR in main_async: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise


def main():
    """Entry point."""
    try:
        asyncio.run(main_async())
    except Exception as e:
        logger.error(f"FATAL ERROR in main: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
