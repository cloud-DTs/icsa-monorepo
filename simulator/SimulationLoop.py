import bisect
import copy
import json
import math
import os
import random
import re
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import boto3

from .domain import Attribute, DataType

CREDENTIALS_PATH = os.path.abspath(os.getenv('CONFIG_CREDENTIALS_JSON', './input/config_credentials.json'))
DEFAULT_AWS_REGION = "eu-central-1"


def safe_float(value, default=0.0):
    if value is None or str(value).strip() == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value, default=0):
    if value is None or str(value).strip() == "":
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def parse_headers(raw_headers: str) -> dict:
    if raw_headers is None:
        return {}

    value = str(raw_headers).strip()
    if not value:
        return {}

    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}

    return parsed if isinstance(parsed, dict) else {}


def extract_json_value(payload, json_path: str):
    if json_path is None or str(json_path).strip() == "":
        return payload

    tokens = re.findall(r'[^.\[\]]+|\[\d+\]', str(json_path).strip())
    current = payload

    for token in tokens:
        if not token:
            continue

        if token.startswith('[') and token.endswith(']'):
            if not isinstance(current, list):
                return None
            index = int(token[1:-1])
            if index < 0 or index >= len(current):
                return None
            current = current[index]
        else:
            if isinstance(current, dict):
                current = current.get(token)
            else:
                return None

        if current is None:
            return None

    return current


def coerce_value(value, dtype: str):
    """Convert a value taken from an API response into the attribute's data type.

    Raises ValueError when the value cannot be represented, so the caller can skip
    the publish. Returning a fallback of 0/0.0/[] would be indistinguishable from a
    genuine reading and would hide the failure.
    """
    if value is None:
        raise ValueError(f"API value is null, cannot convert to {dtype}")

    if dtype == "STRING":
        return str(value)

    if dtype == "BOOLEAN":
        if type(value) is bool:
            return value
        if isinstance(value, str) and value.strip().lower() in ("true", "false"):
            return value.strip().lower() == "true"
        raise ValueError("Boolean values must be true or false")

    if dtype in ("INTEGER", "LONG"):
        if type(value) is int:
            return value
        if type(value) not in (str, float):
            raise ValueError("Integer values must be numeric")
        try:
            number = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError("Integer values must be numeric") from exc
        if not number.is_finite() or number != number.to_integral_value():
            raise ValueError("Integer values must be finite whole numbers")
        return int(number)

    if dtype == "DOUBLE":
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise ValueError(f"API value {value!r} is not numeric")
        try:
            number = float(value)
        except (ValueError, OverflowError) as exc:
            raise ValueError(f"API value {value!r} is not numeric") from exc
        if math.isnan(number) or math.isinf(number):
            raise ValueError(f"API value {value!r} is not a finite number")
        return number

    if dtype.startswith("VECTOR_"):
        if not isinstance(value, list):
            raise ValueError(f"API value {value!r} is not a list, cannot convert to {dtype}")
        base_dtype = dtype.replace("VECTOR_", "")
        return [coerce_value(item, base_dtype) for item in value]

    raise ValueError(f"Unsupported data type: {dtype}")


DEFAULT_API_PROVIDER = {
    "name": "Energy Charts renewable share forecast",
    "url": "https://api.energy-charts.info/ren_share_forecast?country=de",
    "json_path": "ren_share",
    "timestamp_path": "unix_seconds",
}


def fetch_json(url: str, headers: dict, timeout: int):
    request = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw_body = response.read().decode('utf-8')
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        raise RuntimeError(f"API request failed: {exc}") from exc

    try:
        return json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise ValueError("API response is not valid JSON") from exc


def select_current_sample(timestamps: list, values: list, now_epoch: float = None):
    """Pick the (timestamp, value) pair whose timestamp is the newest one at or before now.

    The provider returns a fixed local-day window rather than a rolling one, so the last
    element of the series is a forecast hours ahead, not the current reading. Sibling
    series can also be shorter than unix_seconds, so only the paired prefix is searched.
    """
    if now_epoch is None:
        now_epoch = datetime.now(timezone.utc).timestamp()

    paired = min(len(timestamps), len(values))
    if paired == 0:
        raise ValueError("API response contained no data points")

    index = bisect.bisect_right(timestamps, now_epoch, 0, paired) - 1
    if index < 0:
        raise ValueError("API response has no sample at or before the current time")
    return timestamps[index], values[index]


def fetch_predefined_api_value(dtype: str):
    """Return (value, epoch_seconds) for the current point of the predefined provider."""
    provider = DEFAULT_API_PROVIDER
    payload = fetch_json(provider["url"], {}, 15)

    values = extract_json_value(payload, provider["json_path"])
    if not isinstance(values, list) or not values:
        raise ValueError(f"API response did not contain a '{provider['json_path']}' list")

    timestamps = extract_json_value(payload, provider["timestamp_path"])
    if not isinstance(timestamps, list) or not timestamps:
        raise ValueError(f"API response did not contain a '{provider['timestamp_path']}' list")

    sample_epoch, raw_value = select_current_sample(timestamps, values)
    return coerce_value(raw_value, dtype), sample_epoch


def fetch_api_value(config: dict, dtype: str):
    """Return (value, epoch_seconds) where epoch_seconds is None if the API carries no timestamp."""
    if config.get("api_url"):
        api_url = str(config.get("api_url", "")).strip()
        json_path = config.get("json_path", "")
        timeout = max(1, safe_int(config.get("timeout"), 10))
        headers = parse_headers(config.get("headers", ""))

        payload = fetch_json(api_url, headers, timeout)

        extracted = extract_json_value(payload, json_path)
        if extracted is None:
            raise ValueError("API response field was not found")

        return coerce_value(extracted, dtype), None

    return fetch_predefined_api_value(dtype)


def _number(config, key, dtype, default):
    value = config.get(key)
    return coerce_value(default if value is None or str(value).strip() == "" else value, dtype)


def _vector(value, dtype):
    values = value if isinstance(value, list) else [part.strip() for part in str(value or "").split(",") if part.strip()]
    return [coerce_value(item, dtype) for item in values]


def generate_value(config: dict, dtype: str):
    mode = config.get("mode")

    if dtype.startswith("VECTOR_"):
        base_dtype = dtype[7:]
        if mode == "vector_custom":
            return _vector(config.get("vector", ""), base_dtype)
        elif mode == "vector_uniform" and base_dtype != "STRING":
            min_vec = _vector(config.get("vec_min", ""), base_dtype)
            max_vec = _vector(config.get("vec_max", ""), base_dtype)
            if not min_vec or len(min_vec) != len(max_vec):
                raise ValueError("Vector bounds must have the same nonzero length")
            result = []
            for mn, mx in zip(min_vec, max_vec):
                if mn > mx:
                    raise ValueError("Vector minimum must not exceed its maximum")
                if base_dtype == "DOUBLE":
                    result.append(round(random.uniform(mn, mx), 2))
                else:
                    result.append(random.randint(mn, mx))
            return result

    if dtype in ("INTEGER", "LONG", "DOUBLE"):
        if mode == "uniform":
            mn = _number(config, "min", dtype, 0)
            mx = _number(config, "max", dtype, 100)
            if mn > mx:
                raise ValueError("Minimum must not exceed maximum")
            return round(random.uniform(mn, mx), 2) if dtype == "DOUBLE" else random.randint(mn, mx)
        elif mode == "normal":
            mean = _number(config, "mean", "DOUBLE", 0)
            stddev = _number(config, "stddev", "DOUBLE", 1)
            if stddev < 0:
                raise ValueError("Standard deviation must not be negative")
            val = random.gauss(mean, stddev)
            return round(val, 2) if dtype == "DOUBLE" else int(val)

    if dtype == "BOOLEAN":
        if mode == "fixed":
            return coerce_value(config.get("value", False), dtype)
        if mode == "random_boolean":
            return bool(random.getrandbits(1))

    if dtype == "STRING":
        if mode == "fixed_list":
            raw_list = config.get("list", "low,medium,high")
            words = [x.strip() for x in raw_list.split(",") if x.strip()]
            return random.choice(words) if words else "low"
        elif mode == "random_string":
            return random.choice(["status_ok", "status_warn", "status_error"])

    raise ValueError(f"Unsupported generation mode {mode!r} for {dtype}")


class AWS_CREDENTIALS:
    def __init__(self, credentials_path=CREDENTIALS_PATH):
        if not os.path.exists(credentials_path):
            raise FileNotFoundError(f"Credentials file not found: {credentials_path}")
        with open(credentials_path, 'r', encoding='utf-8-sig') as f:
            self.credentials = json.load(f)


class SimulationLoop:
    def __init__(self, topic: str, region: str | None = None):
        self.topic = topic
        self.mock_aws = _is_enabled(os.getenv("SIMULATOR_MOCK_AWS", "true"))
        self.client = None if self.mock_aws else _create_iot_client(region)
        self.active_runs: dict[str, dict] = {}
        self.sim_time = 10.0
        self._lock = threading.RLock()
        self._last_generation = 0
        self._last_timestamp = {}
        if self.mock_aws:
            print("SIMULATOR_MOCK_AWS is enabled. Payloads will be logged, not published to AWS IoT Core.")

    def is_running(self, attribute_id: str) -> bool:
        with self._lock:
            return self.active_runs.get(attribute_id, {}).get("run", False)

    def error_for(self, attribute_id: str) -> str:
        with self._lock:
            return self.active_runs.get(attribute_id, {}).get("error", "")

    @property
    def sim_time(self):
        return self._sim_time

    @sim_time.setter
    def sim_time(self, value):
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0.1:
            raise ValueError("Simulation interval must be a finite number of at least 0.1 seconds")
        self._sim_time = float(value)

    def _is_active(self, attribute_id: str, generation: int) -> bool:
        """True only for the newest run of this attribute.

        A worker can be asleep when its run is stopped and a new one started. Checking
        the run flag alone is not enough: start_one installs a fresh {"run": True}, so
        the old worker would wake up, see it, and keep publishing alongside the new one.
        """
        with self._lock:
            active_run = self.active_runs.get(attribute_id, {})
            return active_run.get("run", False) and active_run.get("generation") == generation

    def start_one(self, attribute: Attribute, real_device_id: str, config: dict):
        with self._lock:
            if self.is_running(attribute.id):
                return

            self._last_generation += 1
            generation = self._last_generation
            self.active_runs[attribute.id] = {
                "run": True, "generation": generation, "stop_event": threading.Event(),
                "error": "", "attribute": attribute,
            }

        attribute.run = True

        thread = threading.Thread(
            target=self._loop,
            args=(attribute, real_device_id, copy.deepcopy(config), generation),
            daemon=True,
        )
        thread.start()

    def stop_one(self, attribute: Attribute):
        with self._lock:
            if attribute.id in self.active_runs:
                self.active_runs[attribute.id]["run"] = False
                self.active_runs[attribute.id]["stop_event"].set()
        attribute.run = False

    def stop_all(self):
        with self._lock:
            for active_run in self.active_runs.values():
                active_run["run"] = False
                active_run["stop_event"].set()
                if active_run.get("attribute") is not None:
                    active_run["attribute"].run = False

    def _timestamp(self, device_id, sample_epoch):
        if sample_epoch is not None:
            return datetime.fromtimestamp(sample_epoch, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        moment = datetime.now(timezone.utc)
        moment = moment.replace(microsecond=moment.microsecond // 1000 * 1000)
        with self._lock:
            previous = self._last_timestamp.get(device_id)
            if previous is not None and moment <= previous:
                moment = previous + timedelta(milliseconds=1)
            self._last_timestamp[device_id] = moment
        return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def _loop(self, attribute: Attribute, real_device_id: str, config: dict, generation: int):
        with self._lock:
            active_run = self.active_runs[attribute.id]
            stop_event = active_run.setdefault("stop_event", threading.Event())
        try:
            self._run(attribute, real_device_id, config, generation, stop_event)
        except Exception as error:
            with self._lock:
                if self.active_runs[attribute.id]["generation"] == generation:
                    self.active_runs[attribute.id]["error"] = str(error)
            print(f"Simulation failed for {attribute.name}: {error}")
        finally:
            with self._lock:
                if self.active_runs[attribute.id]["generation"] == generation:
                    self.active_runs[attribute.id]["run"] = False
                    attribute.run = False
                    stop_event.set()

    def _run(self, attribute, real_device_id, config, generation, stop_event):
        mode = config.get("mode")
        dtype = attribute.dataType.value

        current_value = None
        mn = mx = step = None
        if mode == "range":
            if dtype not in ("INTEGER", "LONG", "DOUBLE"):
                raise ValueError("Range mode requires a numeric property")
            mn = _number(config, "min", dtype, 0)
            mx = _number(config, "max", dtype, 100)
            step = _number(config, "step", dtype, 1)
            if mn > mx or step <= 0:
                raise ValueError("Range mode requires min <= max and step > 0")
            current_value = mn
        elif mode == "cycle":
            if dtype not in ("INTEGER", "LONG", "DOUBLE"):
                raise ValueError("Cycle mode requires a numeric property")
            current_value = _number(config, "start", "LONG", 0) % 24

        while self._is_active(attribute.id, generation):
            sample_epoch = None

            if mode == "range":
                simulated_value = round(current_value, 2) if dtype == "DOUBLE" else int(current_value)
                current_value += step
                if current_value > mx:
                    current_value = mn
            elif mode == "cycle":
                simulated_value = round(float(current_value), 2) if dtype == "DOUBLE" else int(current_value)
                current_value = (current_value + 1) % 24
            elif mode == "api":
                try:
                    simulated_value, sample_epoch = fetch_api_value(config, dtype)
                except Exception as exc:
                    print(f"API mode failed for {attribute.name}: {exc} - skipping publish")
                    with self._lock:
                        if self.active_runs[attribute.id]["generation"] == generation:
                            self.active_runs[attribute.id]["error"] = str(exc)
                    stop_event.wait(self.sim_time)
                    continue
            else:
                simulated_value = generate_value(config, dtype)

            # API values carry the timestamp of the sample they were read from, so that the
            # published value and time always describe the same point in the series.
            timestamp = self._timestamp(real_device_id, sample_epoch)
            simulated_value = coerce_value(simulated_value, dtype)
            payload_dict = {
                "iotDeviceId": real_device_id,
                "time": timestamp,
                attribute.name: simulated_value,
            }

            # Producing the value can take a moment, so re-check that this run is
            # still the active one right before publishing.
            if not self._is_active(attribute.id, generation):
                break

            print(f"Publishing to {self.topic}: {payload_dict}")
            if self.mock_aws:
                print("Mock AWS publish: 200")
                with self._lock:
                    if self.active_runs[attribute.id]["generation"] == generation:
                        self.active_runs[attribute.id]["error"] = ""
                stop_event.wait(self.sim_time)
                continue

            try:

                response = self.client.publish(
                   topic=self.topic,
                   qos=1,
                   payload=json.dumps(payload_dict, allow_nan=False).encode('utf-8'),
                )
                status = response.get('ResponseMetadata', {}).get('HTTPStatusCode')
                if status != 200:
                    raise RuntimeError(f"AWS IoT publish returned HTTP {status}")
                with self._lock:
                    if self.active_runs[attribute.id]["generation"] == generation:
                        self.active_runs[attribute.id]["error"] = ""
                print(f"AWS Response: {status}")
            except Exception as e:
                with self._lock:
                    if self.active_runs[attribute.id]["generation"] == generation:
                        self.active_runs[attribute.id]["error"] = str(e)
                print(f"Failed to publish to AWS IoT Core: {e}")

            stop_event.wait(self.sim_time)

        print(f"Thread stopped for: {attribute.name} ({attribute.id})")


def _create_iot_client(region: str | None):
    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    if bool(access_key) != bool(secret_key):
        raise ValueError("Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY together")
    selected_region = region or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    if os.getenv("AWS_PROFILE") and not selected_region:
        return boto3.client('iot-data')
    if access_key or os.getenv("AWS_PROFILE") or not os.path.exists(CREDENTIALS_PATH):
        return boto3.client('iot-data', region_name=selected_region or DEFAULT_AWS_REGION)
    creds = AWS_CREDENTIALS(CREDENTIALS_PATH).credentials
    token = {"aws_session_token": creds["aws_session_token"]} if creds.get("aws_session_token") else {}
    return boto3.client(
        'iot-data',
        region_name=selected_region or creds["aws_region"],
        aws_access_key_id=creds["aws_access_key_id"],
        aws_secret_access_key=creds["aws_secret_access_key"],
        **token,
    )


def _is_enabled(value: str | None) -> bool:
    normalized = value.strip().lower() if value is not None else "true"
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError("SIMULATOR_MOCK_AWS must be true or false")
