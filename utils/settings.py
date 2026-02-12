import ctypes
import re
from pathlib import Path
from typing import Dict, Tuple

import toml

try:
    import win32gui
except ImportError:
    win32gui = None

from utils.logger import Logger

# Setup Logging
logger = Logger().get_logger()

config = dict  # autocomplete

COORD_SECTIONS = [
    "HomeBaseStaticClickPositions",
    "BuilderBaseStaticClickPositions",
    "HomeBaseCoordinates",
    "BuilderBaseCoordinates",
    "RecordAttackCoordinates",
    "ObjectDetectionCoordinates",
    "General",
]

SPECIFIC_CONVERSIONS = {
    "HomeBaseGeneral": ["special_troop_drop"]
}

SCALAR_Y_KEYS = [
    "builder_upgrade_step_y",
    "research_upgrade_step_y",
    "builder_upgrade_step_y_small",
    "account_switch_y_offset",
]

SCALAR_X_KEYS = [
    "pet_step_x",
]

def deep_merge(dict1, dict2):
    """
    Recursively merges dict2 into dict1.
    """
    for key, value in dict2.items():
        if isinstance(value, dict) and key in dict1 and isinstance(dict1[key], dict):
            deep_merge(dict1[key], value)
        else:
            dict1[key] = value
    return dict1

def get_target_resolution(logger):
    width, height = 1728, 1080 # Default
    
    # Try detecting window
    if win32gui:
        try:
            found_hwnd = None
            def enum_windows_callback(hwnd, _):
                nonlocal found_hwnd
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if "Clash of Clans" in title: # Partial match
                        found_hwnd = hwnd

            win32gui.EnumWindows(enum_windows_callback, None)

            if found_hwnd:
                # Try to find Child Window (CROSVM)
                child_hwnd = None
                def enum_child_cb(hwnd, _):
                    nonlocal child_hwnd
                    cls_name = win32gui.GetClassName(hwnd)
                    if "CROSVM" in cls_name.upper():
                        child_hwnd = hwnd
                
                try:
                    win32gui.EnumChildWindows(found_hwnd, enum_child_cb, None)
                except Exception:
                    pass
                
                target_hwnd = child_hwnd if child_hwnd else found_hwnd
                target_name = "Child (CROSVM)" if child_hwnd else "Main Window"

                rect = win32gui.GetClientRect(target_hwnd)
                w = rect[2] - rect[0]
                h = rect[3] - rect[1]
                
                if w > 100 and h > 100: # Sanity check
                    logger.debug(f"Detected 'Clash of Clans' {target_name} at {w}x{h}")
                    return w, h
            else:
                 logger.warning("Window 'Clash of Clans' not found.")

        except Exception as e:
            logger.warning(f"Failed to detect window: {e}")

    # Fallback to screen resolution
    try:
        user32 = ctypes.windll.user32
        w = user32.GetSystemMetrics(0)
        h = user32.GetSystemMetrics(1)
        logger.info(f"Fallback to screen resolution: {w}x{h}")
        return w, h
    except Exception as e:
        logger.error(f"Failed to get screen resolution: {e}")
    
    return width, height



def scale_value_recursive(val, w, h, is_y_scalar=False, is_x_scalar=False):
    if isinstance(val, (int, float)):
        if is_y_scalar:
            return int(round(val * h))
        if is_x_scalar:
            return int(round(val * w))
        return val # Should usually be inside list for coords, but if lone scalar, leave as is unless scalar flag set
    
    if isinstance(val, list):
        new_list = []
        for i, item in enumerate(val):
            if isinstance(item, list):
                new_list.append(scale_value_recursive(item, w, h))
            elif isinstance(item, dict):
                 new_dict = item.copy()
                 for k, v in item.items():
                     if k == 'region':
                         new_dict[k] = scale_value_recursive(v, w, h)
                 new_list.append(new_dict)
            elif isinstance(item, (int, float)):
                # Assume [x, y] or [x1, y1, x2, y2]
                if i % 2 == 0: # X
                    new_list.append(int(round(item * w)))
                else: # Y
                    new_list.append(int(round(item * h)))
            else:
                new_list.append(item)
        return new_list
    
    return val

def crawl(obj: dict, func=lambda x, y: logger.info(f"{x} {y}"), path=None):
    if path is None:  # path Default argument value is mutable
        path = []
    for key in obj.keys():
        if type(obj[key]) is dict:
            crawl(obj[key], func, path + [key])
            continue
        func(path + [key], obj[key])


def check(value, checks, name):

    def get_check_value(key, default_result):
        return checks[key] if key in checks else default_result

    incorrect = False
    if value == {}:
        incorrect = True
    if not incorrect and "type" in checks:
        try:
            value = eval(checks["type"])(value)
        except:
            incorrect = True
    # FAILSTATE Value is not one of the options
    if not incorrect and "options" in checks and value not in checks["options"]:
        incorrect = True
    # FAILSTATE Value doesn't match regex, or has regex but is not a string.
    if (
        not incorrect
        and "regex" in checks
        and (
            (isinstance(value, str) and re.match(checks["regex"], value) is None)
            or not isinstance(value, str)
        )
    ):
        incorrect = True

    if (
        not incorrect
        and not hasattr(value, "__iter__")
        and (
            ("nmin" in checks and checks["nmin"] is not None and value < checks["nmin"])
            or (
                "nmax" in checks
                and checks["nmax"] is not None
                and value > checks["nmax"]
            )
        )
    ):
        incorrect = True
    if (
        not incorrect
        and hasattr(value, "__iter__")
        and (
            (
                "nmin" in checks
                and checks["nmin"] is not None
                and len(value) < checks["nmin"]
            )
            or (
                "nmax" in checks
                and checks["nmax"] is not None
                and len(value) > checks["nmax"]
            )
        )
    ):
        incorrect = True

    if incorrect:
        value = handle_input(
            message=(
                (
                    ("\nExample: " + str(checks["example"]) + "\n")
                    if "example" in checks
                    else ""
                )
                + ("Non-optional ", "Optional ")[
                    "optional" in checks and checks["optional"] is True
                ]
            )
            + str(name),
            extra_info=get_check_value("explanation", ""),
            check_type=eval(get_check_value("type", "False")),
            default=get_check_value("default", NotImplemented),
            match=get_check_value("regex", ""),
            err_message=get_check_value("input_error", "Incorrect input"),
            nmin=get_check_value("nmin", None),
            nmax=get_check_value("nmax", None),
            oob_error=get_check_value(
                "oob_error", "Input out of bounds(Value too high/low/long/short)"
            ),
            options=get_check_value("options", None),
            optional=get_check_value("optional", False),
        )
    return value


def handle_input(
    message: str = "",
    check_type=False,
    match: str = "",
    err_message: str = "",
    nmin=None,
    nmax=None,
    oob_error="",
    extra_info="",
    options: list = None,
    default=NotImplemented,
    optional=False,
):
    if optional:
        logger.info(message + "\nThis is an optional value. Do you want to skip it? (y/n)")
        if input().casefold().startswith("y"):
            return default if default is not NotImplemented else ""
    if default is not NotImplemented:
        logger.info(
            message
            + '\nThe default value is "'
            + str(default)
            + '"\nDo you want to use it?(y/n)'
        )
        if input().casefold().startswith("y"):
            return default
    if options is None:
        match = re.compile(match)
        logger.info(extra_info)
        while True:
            # print(message + "=", end="") replaced by input prompt
            user_input = input(message + "=").strip()
            if check_type is not False:
                try:
                    user_input = check_type(user_input)
                    if (nmin is not None and user_input < nmin) or (
                        nmax is not None and user_input > nmax
                    ):
                        # FAILSTATE Input out of bounds
                        logger.warning(oob_error)
                        continue
                    break  # Successful type conversion and number in bounds
                except ValueError:
                    # Type conversion failed
                    logger.error(err_message)
                    continue
            elif match != "" and re.match(match, user_input) is None:
                logger.warning(+err_message + "\nAre you absolutely sure it's correct?(y/n)")
                if input().casefold().startswith("y"):
                    break
                continue
            else:
                # FAILSTATE Input STRING out of bounds
                if (nmin is not None and len(user_input) < nmin) or (
                    nmax is not None and len(user_input) > nmax
                ):
                    logger.warning(oob_error)
                    continue
                break  # SUCCESS Input STRING in bounds
        return user_input
    logger.info(extra_info)
    while True:
        # print(message, end="") replaced by input prompt
        user_input = input(message).strip()
        if check_type is not False:
            try:
                isinstance(eval(user_input), check_type)
                return check_type(user_input)
            except:
                logger.error(
                    err_message
                    + "\nValid options are: "
                    + ", ".join(map(str, options))
                    + "."
                )
                continue
        if user_input in options:
            return user_input
        logger.warning(
            err_message + "\nValid options are: " + ", ".join(map(str, options)) + "."
        )


def crawl_and_check(obj: dict, path: list, checks: dict = {}, name=""):
    if len(path) == 0:
        return check(obj, checks, name)
    if path[0] not in obj.keys():
        obj[path[0]] = {}
    obj[path[0]] = crawl_and_check(obj[path[0]], path[1:], checks, path[0])
    return obj


def check_vars(path, checks):
    global config
    crawl_and_check(config, path, checks)


def check_toml(template_file, config_file) -> Tuple[bool, Dict]:
    global config, check_vars
    config = None

    # attempt to load template file
    try:
        template = toml.load(template_file)
    except Exception as error:
        logger.error(f"Encountered error when trying to to load {template_file}: {error}")
        logger.error(error)
        return False

    # attempt to config template file
    try:
        config = toml.load(config_file)
    # if file can't be read
    except toml.TomlDecodeError:
        logger.warning(f"""Couldn't read {config_file}.Overwrite it?(y/n)""")
        # attempt to overwrite config file
        if not input().startswith("y"):
            logger.error("Unable to read config, and not allowed to overwrite it. Giving up.")
            return False
        else:
            try:
                with open(config_file, "w") as f:
                    f.write("")
            except:
                logger.error(
                    f"Failed to overwrite {config_file}. Giving up.\nSuggestion: check {config_file} permissions for the user."
                )
                return False
    # if file isn't found
    except FileNotFoundError:
        logger.warning(f"""Couldn't find {config_file} Creating it now.""")
        try:
            with open(config_file, "x") as f:
                f.write("")
            config = {}
        except:
            logger.error(
                f"Failed to write to {config_file}. Giving up.\nSuggestion: check the folder's permissions for the user."
            )
            return False

    logger.debug("Checking TOML configuration...")

    crawl(template, check_vars)
    with open(config_file, "w") as f:
        toml.dump(config, f)
    return config


directory = Path(__file__).resolve().parent.parent
check_toml(directory / "config.template.toml", directory / "config.toml")

# Load static config
# test_static_config_path = directory / "utils" / "baseconfig" / "test_static_config.toml"
static_config_path = directory / "utils" / "baseconfig" / "static_config.toml"


def scale_config(conf, w, h):
    """
    Recursively scales a configuration dictionary from percentage values to pixels.
    Mutates the dictionary in-place.
    """
    for section_name, section_data in conf.items():
        # Heuristic: if section name ends with "Attacks" or contains coordinates, scale it.
        # Checking against known sections from baseconfig and static_config
        if section_name.endswith("Attacks") or section_name.endswith("Positions") or section_name in COORD_SECTIONS or section_name in ["HomeBaseAttacks", "BuilderBaseAttacks", "HomeBaseDynamicClickPositions", "BuilderBaseDynamicClickPositions"]:
             if isinstance(section_data, dict):
                 for key, value in section_data.items():
                     is_y = (key in SCALAR_Y_KEYS)
                     is_x = (key in SCALAR_X_KEYS)
                     conf[section_name][key] = scale_value_recursive(value, w, h, is_y_scalar=is_y, is_x_scalar=is_x)
        elif section_name in SPECIFIC_CONVERSIONS:
            for key in SPECIFIC_CONVERSIONS[section_name]:
                 if key in section_data:
                      conf[section_name][key] = scale_value_recursive(section_data[key], w, h)

# Decision logic: static_config.toml is now percentage-based
if static_config_path.exists():
    try:
        static_conf = toml.load(static_config_path)
        logger.debug(f"Loaded config from {static_config_path}")
        
        # Determine actual resolution
        w, h = get_target_resolution(logger)
        
        # Scale values using helper
        scale_config(static_conf, w, h)
        
        deep_merge(config, static_conf)
        logger.debug(f"Deep merged static config to {w}x{h}")
        
    except Exception as e:
        logger.error(f"Error loading/scaling static config: {e}")
else:
    logger.error(f"static_config.toml not found at {static_config_path}")

# Update Logger Level from final config
if config.get("General") and config["General"].get("LogLevel"):
    new_level = config["General"]["LogLevel"].upper()
    try:
        # Re-setting the level on the global logger
        logger.setLevel(new_level)
        # We don't need to re-import Logger here as it's not used, just logger.setLevel
        logger.debug(f"Logger level set to {new_level} from config.")
    except Exception as e:
        logger.error(f"Failed to set log level to {new_level}: {e}")

