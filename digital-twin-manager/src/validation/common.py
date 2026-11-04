def require_dict(value, field):
  if not isinstance(value, dict):
    raise ValueError(f"{field} must be a JSON object.")


def require_list(value, field):
  if not isinstance(value, list):
    raise ValueError(f"{field} must be a JSON array.")


def require_keys(value, required_keys, field):
  missing_keys = required_keys - value.keys()

  if missing_keys:
    raise ValueError(
      f"{field} is missing required key(s): {keys_text(missing_keys)}"
    )


def require_no_unknown_keys(value, allowed_keys, field):
  unknown_keys = value.keys() - allowed_keys

  if unknown_keys:
    raise ValueError(
      f"{field} contains unknown key(s): {keys_text(unknown_keys)}"
    )


def require_string(value, field):
  if not isinstance(value, str):
    raise ValueError(f"{field} must be a string.")

  if not value:
    raise ValueError(f"{field} must not be empty.")


def require_bool(value, field):
  if not isinstance(value, bool):
    raise ValueError(f"{field} must be a boolean.")


def require_positive_int(value, field):
  if isinstance(value, bool) or not isinstance(value, int):
    raise ValueError(f"{field} must be an integer.")

  if value <= 0:
    raise ValueError(f"{field} must be greater than 0.")


def keys_text(keys):
  return ", ".join(sorted(keys))
