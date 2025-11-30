#!/usr/bin/env python3
"""Continuous Log Generator

A containerized log generator that continuously produces realistic random logs
for testing the anomaly detection framework.

Features:
- Continuous log generation with configurable rate
- Realistic HTTP access logs using Faker
- Configurable anomaly injection
- Time-aware patterns (workday vs weekend, hour-based)
- Multiple log formats (JSON, Apache-style, custom)

Environment Variables:
    LOG_OUTPUT_DIR: Directory to write logs (default: /var/log/app-logs)
    LOG_FILE_NAME: Base name for log files (default: app-logs)
    LOGS_PER_MINUTE: Target logs per minute (default: 60)
    ANOMALY_PROBABILITY: Probability of anomaly per log (default: 0.01)
    LOG_FORMAT: Format type: json, apache, custom (default: json)
    SEED: Random seed for reproducibility (optional)
    BURST_ENABLED: Enable random traffic bursts (default: true)
    WORKDAY_PATTERN: Enable workday traffic patterns (default: true)

Usage:
    # Run directly
    python continuous_log_generator.py
    
    # Run in Docker
    docker run -v /path/to/logs:/var/log/app-logs log-generator
"""

import os
import sys
import json
import time
import random
import signal
import logging
import argparse
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
from collections import OrderedDict
from pathlib import Path

# Try to import faker, provide fallback
try:
    from faker import Faker
    FAKER_AVAILABLE = True
except ImportError:
    FAKER_AVAILABLE = False
    print("Warning: Faker not installed. Using basic random generation.", file=sys.stderr)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


@dataclass
class LogGeneratorConfig:
    """Configuration for the continuous log generator."""
    
    output_dir: str = "/var/log/app-logs"
    log_file_name: str = "app-logs"
    logs_per_minute: int = 60
    anomaly_probability: float = 0.01
    log_format: str = "json"  # json, apache, custom
    seed: Optional[int] = None
    burst_enabled: bool = True
    workday_pattern: bool = True
    rotate_size_mb: int = 10
    max_files: int = 5
    
    # Anomaly configuration
    anomaly_request_count_min: int = 5000
    anomaly_request_count_max: int = 10000
    anomaly_error_rate: float = 0.5
    anomaly_latency_multiplier: float = 10.0
    
    @classmethod
    def from_env(cls) -> "LogGeneratorConfig":
        """Create config from environment variables."""
        return cls(
            output_dir=os.getenv("LOG_OUTPUT_DIR", "/var/log/app-logs"),
            log_file_name=os.getenv("LOG_FILE_NAME", "app-logs"),
            logs_per_minute=int(os.getenv("LOGS_PER_MINUTE", "60")),
            anomaly_probability=float(os.getenv("ANOMALY_PROBABILITY", "0.01")),
            log_format=os.getenv("LOG_FORMAT", "json"),
            seed=int(os.getenv("SEED")) if os.getenv("SEED") else None,
            burst_enabled=os.getenv("BURST_ENABLED", "true").lower() == "true",
            workday_pattern=os.getenv("WORKDAY_PATTERN", "true").lower() == "true",
            rotate_size_mb=int(os.getenv("ROTATE_SIZE_MB", "10")),
            max_files=int(os.getenv("MAX_FILES", "5")),
            anomaly_request_count_min=int(os.getenv("ANOMALY_REQUEST_COUNT_MIN", "5000")),
            anomaly_request_count_max=int(os.getenv("ANOMALY_REQUEST_COUNT_MAX", "10000")),
            anomaly_error_rate=float(os.getenv("ANOMALY_ERROR_RATE", "0.5")),
            anomaly_latency_multiplier=float(os.getenv("ANOMALY_LATENCY_MULTIPLIER", "10.0")),
        )


class FakeDataGenerator:
    """Generates realistic fake data for logs."""
    
    def __init__(self, seed: Optional[int] = None):
        self.seed = seed
        if seed is not None:
            random.seed(seed)
        
        if FAKER_AVAILABLE:
            self.fake = Faker()
            if seed is not None:
                Faker.seed(seed)
        else:
            self.fake = None
        
        # HTTP methods with realistic weights
        self.http_methods = OrderedDict([
            ("GET", 0.70),
            ("POST", 0.20),
            ("PUT", 0.05),
            ("DELETE", 0.03),
            ("PATCH", 0.02),
        ])
        
        # Status codes with realistic weights
        self.status_codes_normal = OrderedDict([
            (200, 0.85),
            (201, 0.05),
            (204, 0.03),
            (301, 0.02),
            (302, 0.02),
            (304, 0.02),
            (400, 0.005),
            (404, 0.005),
        ])
        
        self.status_codes_anomaly = OrderedDict([
            (500, 0.40),
            (502, 0.20),
            (503, 0.20),
            (504, 0.10),
            (400, 0.05),
            (403, 0.03),
            (429, 0.02),
        ])
        
        # Common API endpoints
        self.endpoints = [
            "/api/v1/users",
            "/api/v1/users/{id}",
            "/api/v1/products",
            "/api/v1/products/{id}",
            "/api/v1/orders",
            "/api/v1/orders/{id}",
            "/api/v1/auth/login",
            "/api/v1/auth/logout",
            "/api/v1/auth/refresh",
            "/api/v1/search",
            "/api/v1/cart",
            "/api/v1/checkout",
            "/api/v1/payments",
            "/api/v1/notifications",
            "/api/v2/analytics",
            "/api/v2/reports",
            "/health",
            "/metrics",
            "/ready",
        ]
        
        # User agents
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 Safari/17.0",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
            "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120.0.0.0",
            "PostmanRuntime/7.35.0",
            "python-requests/2.31.0",
            "axios/1.6.0",
            "curl/8.4.0",
        ]
    
    def weighted_choice(self, choices: OrderedDict) -> Any:
        """Select from weighted choices."""
        items = list(choices.keys())
        weights = list(choices.values())
        return random.choices(items, weights=weights, k=1)[0]
    
    def generate_ip(self) -> str:
        """Generate a random IP address."""
        if self.fake:
            return self.fake.ipv4()
        return f"{random.randint(1,255)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"
    
    def generate_user_agent(self) -> str:
        """Generate a random user agent."""
        if self.fake:
            return self.fake.user_agent()
        return random.choice(self.user_agents)
    
    def generate_endpoint(self) -> str:
        """Generate a random API endpoint."""
        endpoint = random.choice(self.endpoints)
        # Replace {id} placeholders with random IDs
        if "{id}" in endpoint:
            endpoint = endpoint.replace("{id}", str(random.randint(1, 99999)))
        return endpoint
    
    def generate_http_method(self) -> str:
        """Generate a weighted random HTTP method."""
        return self.weighted_choice(self.http_methods)
    
    def generate_status_code(self, is_anomaly: bool = False) -> int:
        """Generate a weighted random status code."""
        if is_anomaly:
            return self.weighted_choice(self.status_codes_anomaly)
        return self.weighted_choice(self.status_codes_normal)
    
    def generate_latency(self, is_anomaly: bool = False, base_latency: float = 50.0) -> float:
        """Generate realistic latency in milliseconds."""
        if is_anomaly:
            # Anomaly: very high latency
            return base_latency * random.uniform(5.0, 20.0) + random.uniform(1000, 5000)
        
        # Normal distribution around base latency
        latency = random.gauss(base_latency, base_latency * 0.3)
        return max(1.0, latency)  # Minimum 1ms
    
    def generate_bytes(self, method: str, status: int) -> int:
        """Generate realistic response size in bytes."""
        if status == 204:
            return 0
        if status >= 400:
            return random.randint(100, 500)
        if method == "GET":
            return random.randint(500, 50000)
        if method == "POST":
            return random.randint(100, 5000)
        return random.randint(100, 2000)
    
    def generate_request_count(self, is_anomaly: bool = False, config: LogGeneratorConfig = None) -> int:
        """Generate request count for aggregated metrics."""
        if is_anomaly and config:
            return random.randint(config.anomaly_request_count_min, config.anomaly_request_count_max)
        # Normal: follows time-of-day pattern
        return random.randint(100, 2000)
    
    def generate_error_count(self, request_count: int, is_anomaly: bool = False, config: LogGeneratorConfig = None) -> int:
        """Generate error count based on request count."""
        if is_anomaly and config:
            error_rate = config.anomaly_error_rate
        else:
            error_rate = random.uniform(0.001, 0.02)  # 0.1% - 2% normal error rate
        
        return int(request_count * error_rate)
    
    def generate_session_id(self) -> str:
        """Generate a session ID."""
        if self.fake:
            return self.fake.uuid4()[:8]
        return f"{random.randint(10000000, 99999999):08x}"
    
    def generate_user_id(self) -> Optional[str]:
        """Generate an optional user ID."""
        if random.random() < 0.7:  # 70% of requests have user
            return f"user_{random.randint(1, 10000)}"
        return None


class ContinuousLogGenerator:
    """Generates logs continuously with realistic patterns."""
    
    def __init__(self, config: LogGeneratorConfig):
        self.config = config
        self.data_gen = FakeDataGenerator(config.seed)
        self.running = True
        self.log_count = 0
        self.anomaly_count = 0
        self.current_file: Optional[Path] = None
        self.current_file_size = 0
        self.file_index = 0
        
        # Set up signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Create output directory
        Path(config.output_dir).mkdir(parents=True, exist_ok=True)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
    
    def _get_log_file(self) -> Path:
        """Get current log file, rotating if necessary."""
        output_dir = Path(self.config.output_dir)
        
        # Check if we need to rotate
        if self.current_file and self.current_file.exists():
            self.current_file_size = self.current_file.stat().st_size
            if self.current_file_size >= self.config.rotate_size_mb * 1024 * 1024:
                self._rotate_files()
        
        if self.current_file is None:
            self.current_file = output_dir / f"{self.config.log_file_name}.log"
        
        return self.current_file
    
    def _rotate_files(self):
        """Rotate log files."""
        output_dir = Path(self.config.output_dir)
        base_name = self.config.log_file_name
        
        # Delete oldest file if we're at max
        oldest = output_dir / f"{base_name}.{self.config.max_files}.log"
        if oldest.exists():
            oldest.unlink()
        
        # Rotate existing files
        for i in range(self.config.max_files - 1, 0, -1):
            old_file = output_dir / f"{base_name}.{i}.log"
            new_file = output_dir / f"{base_name}.{i + 1}.log"
            if old_file.exists():
                old_file.rename(new_file)
        
        # Rename current file
        if self.current_file and self.current_file.exists():
            rotated = output_dir / f"{base_name}.1.log"
            self.current_file.rename(rotated)
        
        # Reset current file
        self.current_file = output_dir / f"{base_name}.log"
        self.current_file_size = 0
        logger.info(f"Rotated log files")
    
    def _get_traffic_multiplier(self) -> float:
        """Get traffic multiplier based on time patterns."""
        if not self.config.workday_pattern:
            return 1.0
        
        now = datetime.now()
        hour = now.hour
        is_weekday = now.weekday() < 5
        
        # Base multipliers by hour (simulating business hours)
        hourly_pattern = {
            0: 0.1, 1: 0.05, 2: 0.05, 3: 0.05, 4: 0.05, 5: 0.1,
            6: 0.2, 7: 0.4, 8: 0.7, 9: 0.9, 10: 1.0, 11: 1.0,
            12: 0.8, 13: 0.9, 14: 1.0, 15: 1.0, 16: 0.9, 17: 0.7,
            18: 0.5, 19: 0.4, 20: 0.3, 21: 0.2, 22: 0.15, 23: 0.1,
        }
        
        multiplier = hourly_pattern.get(hour, 0.5)
        
        # Weekend has lower traffic
        if not is_weekday:
            multiplier *= 0.3
        
        return multiplier
    
    def _should_generate_anomaly(self) -> bool:
        """Determine if this log should be an anomaly."""
        return random.random() < self.config.anomaly_probability
    
    def _generate_log_entry(self, is_anomaly: bool = False) -> Dict[str, Any]:
        """Generate a single log entry."""
        now = datetime.now(timezone.utc)
        
        method = self.data_gen.generate_http_method()
        status = self.data_gen.generate_status_code(is_anomaly)
        endpoint = self.data_gen.generate_endpoint()
        latency = self.data_gen.generate_latency(is_anomaly)
        
        entry = {
            "@timestamp": now.isoformat(),
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "level": "ERROR" if status >= 500 else ("WARN" if status >= 400 else "INFO"),
            "http_method": method,
            "http_version": "1.1",
            "url": endpoint,
            "status": status,
            "duration_ms": round(latency, 2),
            "bytes": self.data_gen.generate_bytes(method, status),
            "client_ip": self.data_gen.generate_ip(),
            "user_agent": self.data_gen.generate_user_agent(),
            "session_id": self.data_gen.generate_session_id(),
            "request_id": f"req_{random.randint(100000, 999999)}",
        }
        
        # Add user_id if authenticated
        user_id = self.data_gen.generate_user_id()
        if user_id:
            entry["user_id"] = user_id
        
        # Add anomaly marker for tracking (can be filtered out)
        if is_anomaly:
            entry["_anomaly"] = True
        
        return entry
    
    def _generate_aggregated_entry(self, is_anomaly: bool = False) -> Dict[str, Any]:
        """Generate an aggregated metrics entry (for time-series testing)."""
        now = datetime.now(timezone.utc)
        
        request_count = self.data_gen.generate_request_count(is_anomaly, self.config)
        error_count = self.data_gen.generate_error_count(request_count, is_anomaly, self.config)
        
        entry = {
            "@timestamp": now.isoformat(),
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "request_count": request_count,
            "error_count": error_count,
            "error_rate": round(error_count / max(request_count, 1), 4),
            "avg_latency_ms": round(self.data_gen.generate_latency(is_anomaly), 2),
            "p95_latency_ms": round(self.data_gen.generate_latency(is_anomaly) * 2.5, 2),
            "p99_latency_ms": round(self.data_gen.generate_latency(is_anomaly) * 4.0, 2),
            "bytes_sent": request_count * random.randint(500, 5000),
            "active_users": random.randint(10, 500),
            "is_workday": 1 if datetime.now().weekday() < 5 else 0,
            "hour": datetime.now().hour,
        }
        
        if is_anomaly:
            entry["_anomaly"] = True
        
        return entry
    
    def _format_log(self, entry: Dict[str, Any]) -> str:
        """Format log entry based on configured format."""
        if self.config.log_format == "json":
            return json.dumps(entry)
        
        elif self.config.log_format == "apache":
            # Apache Combined Log Format
            return (
                f'{entry.get("client_ip", "-")} - '
                f'{entry.get("user_id", "-")} '
                f'[{entry.get("timestamp", "-")}] '
                f'"{entry.get("http_method", "GET")} {entry.get("url", "/")} HTTP/{entry.get("http_version", "1.1")}" '
                f'{entry.get("status", 200)} {entry.get("bytes", 0)} '
                f'"-" "{entry.get("user_agent", "-")}"'
            )
        
        elif self.config.log_format == "custom":
            # Custom format matching logstash parser expectations
            level = entry.get("level", "INFO")
            timestamp = entry.get("timestamp", "")
            msg = (
                f'Request finished HTTP/{entry.get("http_version", "1.1")} '
                f'{entry.get("http_method", "GET")} {entry.get("url", "/")} '
                f'- {entry.get("status", 200)} null application/json '
                f'{entry.get("duration_ms", 0)}ms'
            )
            return f"{timestamp} -00:00 [{level}] {msg}"
        
        else:
            return json.dumps(entry)
    
    def _write_log(self, entry: Dict[str, Any]):
        """Write a log entry to the file."""
        log_file = self._get_log_file()
        log_line = self._format_log(entry)
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")
        
        self.current_file_size += len(log_line) + 1
    
    def _generate_burst(self) -> int:
        """Potentially generate a traffic burst, return extra logs to generate."""
        if not self.config.burst_enabled:
            return 0
        
        # 1% chance of burst per minute
        if random.random() < 0.01:
            burst_size = random.randint(50, 200)
            logger.info(f"Generating traffic burst: {burst_size} extra logs")
            return burst_size
        
        return 0
    
    def run(self):
        """Run the continuous log generator."""
        logger.info(f"Starting continuous log generator")
        logger.info(f"  Output: {self.config.output_dir}/{self.config.log_file_name}.log")
        logger.info(f"  Rate: ~{self.config.logs_per_minute} logs/minute")
        logger.info(f"  Format: {self.config.log_format}")
        logger.info(f"  Anomaly probability: {self.config.anomaly_probability * 100:.1f}%")
        logger.info(f"  Workday patterns: {self.config.workday_pattern}")
        logger.info(f"  Bursts enabled: {self.config.burst_enabled}")
        
        # Calculate base interval between logs
        base_interval = 60.0 / self.config.logs_per_minute
        
        last_stats_time = time.time()
        stats_interval = 60  # Print stats every minute
        
        while self.running:
            try:
                # Get traffic multiplier for time-based patterns
                multiplier = self._get_traffic_multiplier()
                
                # Adjust interval based on traffic pattern
                current_interval = base_interval / max(multiplier, 0.1)
                
                # Add some randomness to interval
                actual_interval = current_interval * random.uniform(0.5, 1.5)
                
                # Check for burst
                burst_logs = self._generate_burst()
                
                # Generate logs
                logs_to_generate = 1 + burst_logs
                
                for _ in range(logs_to_generate):
                    is_anomaly = self._should_generate_anomaly()
                    
                    # Use aggregated format for ARMAX testing, otherwise regular
                    if os.getenv("AGGREGATED_MODE", "false").lower() == "true":
                        entry = self._generate_aggregated_entry(is_anomaly)
                    else:
                        entry = self._generate_log_entry(is_anomaly)
                    
                    self._write_log(entry)
                    self.log_count += 1
                    
                    if is_anomaly:
                        self.anomaly_count += 1
                
                # Print periodic stats
                current_time = time.time()
                if current_time - last_stats_time >= stats_interval:
                    logger.info(
                        f"Stats: {self.log_count} logs generated, "
                        f"{self.anomaly_count} anomalies "
                        f"({self.anomaly_count / max(self.log_count, 1) * 100:.2f}%)"
                    )
                    last_stats_time = current_time
                
                # Sleep before next log
                time.sleep(actual_interval)
                
            except Exception as e:
                logger.error(f"Error generating log: {e}")
                time.sleep(1)
        
        # Final stats
        logger.info(f"Shutting down. Total: {self.log_count} logs, {self.anomaly_count} anomalies")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Continuous Log Generator")
    parser.add_argument("--output-dir", default=None, help="Output directory for logs")
    parser.add_argument("--file-name", default=None, help="Base name for log files")
    parser.add_argument("--logs-per-minute", type=int, default=None, help="Target logs per minute")
    parser.add_argument("--anomaly-prob", type=float, default=None, help="Anomaly probability (0-1)")
    parser.add_argument("--format", choices=["json", "apache", "custom"], default=None)
    parser.add_argument("--seed", type=int, default=None, help="Random seed")
    parser.add_argument("--no-bursts", action="store_true", help="Disable traffic bursts")
    parser.add_argument("--no-patterns", action="store_true", help="Disable workday patterns")
    
    args = parser.parse_args()
    
    # Load config from environment, override with CLI args
    config = LogGeneratorConfig.from_env()
    
    if args.output_dir:
        config.output_dir = args.output_dir
    if args.file_name:
        config.log_file_name = args.file_name
    if args.logs_per_minute:
        config.logs_per_minute = args.logs_per_minute
    if args.anomaly_prob is not None:
        config.anomaly_probability = args.anomaly_prob
    if args.format:
        config.log_format = args.format
    if args.seed:
        config.seed = args.seed
    if args.no_bursts:
        config.burst_enabled = False
    if args.no_patterns:
        config.workday_pattern = False
    
    # Run generator
    generator = ContinuousLogGenerator(config)
    generator.run()


if __name__ == "__main__":
    main()
