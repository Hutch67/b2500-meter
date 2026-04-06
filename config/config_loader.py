import configparser
from ipaddress import IPv4Network, IPv4Address
from typing import List, Union, Tuple
from config.logger import logger


def safe_getboolean(config: configparser.ConfigParser, section: str, option: str, fallback: bool) -> bool:
    """Like config.getboolean but logs a warning and uses fallback on invalid values."""
    try:
        return config.getboolean(section, option, fallback=fallback)
    except ValueError:
        raw = config.get(section, option, fallback=str(fallback))
        logger.warning(
            f"Invalid boolean value '{raw}' for [{section}] {option}; using fallback '{fallback}'"
        )
        return fallback


def safe_getint(config: configparser.ConfigParser, section: str, option: str, fallback: int) -> int:
    """Like config.getint but logs a warning and uses fallback on invalid values."""
    try:
        return config.getint(section, option, fallback=fallback)
    except ValueError:
        raw = config.get(section, option, fallback=str(fallback))
        logger.warning(
            f"Invalid integer value '{raw}' for [{section}] {option}; using fallback '{fallback}'"
        )
        return fallback


def safe_getfloat(config: configparser.ConfigParser, section: str, option: str, fallback: float) -> float:
    """Like config.getfloat but logs a warning and uses fallback on invalid values."""
    try:
        return config.getfloat(section, option, fallback=fallback)
    except ValueError:
        raw = config.get(section, option, fallback=str(fallback))
        logger.warning(
            f"Invalid float value '{raw}' for [{section}] {option}; using fallback '{fallback}'"
        )
        return fallback

from powermeter import (
    Powermeter,
    Tasmota,
    Shelly1PM,
    ShellyPlus1PM,
    ShellyEM,
    Shelly3EM,
    Shelly3EMPro,
    Shrdzm,
    Emlog,
    IoBroker,
    HomeAssistant,
    VZLogger,
    AmisReader,
    ModbusPowermeter,
    MqttPowermeter,
    Script,
    ESPHome,
    JsonHttpPowermeter,
    TQEnergyManager,
    ThrottledPowermeter,
    ExponentialMovingAveragePowermeter,
    OffsetPowermeter,
    SlewRatePowermeter,
    DeadBandPowermeter,
    HoldTimerPowermeter,
)

SHELLY_SECTION = "SHELLY"
TASMOTA_SECTION = "TASMOTA"
SHRDZM_SECTION = "SHRDZM"
EMLOG_SECTION = "EMLOG"
IOBROKER_SECTION = "IOBROKER"
HOMEASSISTANT_SECTION = "HOMEASSISTANT"
VZLOGGER_SECTION = "VZLOGGER"
SCRIPT_SECTION = "SCRIPT"
ESPHOME_SECTION = "ESPHOME"
AMIS_READER_SECTION = "AMIS_READER"
MODBUS_SECTION = "MODBUS"
JSON_HTTP_SECTION = "JSON_HTTP"
TQ_EM_SECTION = "TQ_EM"


class ClientFilter:
    def __init__(self, netmasks: List[IPv4Network]):
        self.netmasks = netmasks

    def matches(self, client_ip) -> bool:
        try:
            client_ip_addr = IPv4Address(client_ip)
            for netmask in self.netmasks:
                if client_ip_addr in netmask:
                    return True
        except ValueError as e:
            logger.error(f"Error: {e}")
            return False


def read_all_powermeter_configs(
    config: configparser.ConfigParser,
) -> List[Tuple[Powermeter, ClientFilter]]:
    powermeters = []
    global_throttle_interval = safe_getfloat(
        config, "GENERAL", "THROTTLE_INTERVAL", fallback=0.0
    )
    global_ema_alpha = safe_getfloat(config, "GENERAL", "EMA_ALPHA", fallback=0.0)
    global_ema_interval = safe_getfloat(config, "GENERAL", "EMA_INTERVAL", fallback=0.0)
    global_slew_rate = safe_getfloat(
        config, "GENERAL", "SLEW_RATE_WATTS_PER_SEC", fallback=0.0
    )
    global_deadband_watts = safe_getfloat(config, "GENERAL", "DEADBAND_WATTS", fallback=0.0)
    global_hold_time = safe_getfloat(config, "GENERAL", "HOLD_TIME", fallback=0.0)
    global_power_offset = safe_getfloat(config, "GENERAL", "POWER_OFFSET", fallback=0.0)

    for section in config.sections():
        powermeter = create_powermeter(section, config)
        if powermeter is not None:
            section_throttle_interval = safe_getfloat(
                config, section, "THROTTLE_INTERVAL", fallback=global_throttle_interval
            )

            if section_throttle_interval > 0:
                throttle_source = (
                    "section-specific"
                    if config.has_option(section, "THROTTLE_INTERVAL")
                    else "global"
                )
                print(
                    f"Applying {throttle_source} throttling ({section_throttle_interval}s) to {section}"
                )
                powermeter = ThrottledPowermeter(powermeter, section_throttle_interval)

            section_ema_alpha = safe_getfloat(
                config, section, "EMA_ALPHA", fallback=global_ema_alpha
            )
            if section_ema_alpha > 0:
                if section_ema_alpha > 1.0:
                    raise ValueError(
                        f"EMA_ALPHA in [{section}] must be in the range (0, 1], got {section_ema_alpha}"
                    )
                ema_source = (
                    "section-specific"
                    if config.has_option(section, "EMA_ALPHA")
                    else "global"
                )
                section_ema_interval = safe_getfloat(
                    config, section, "EMA_INTERVAL", fallback=global_ema_interval
                )
                if section_ema_interval > 0:
                    ema_interval_source = (
                        "section-specific"
                        if config.has_option(section, "EMA_INTERVAL")
                        else "global"
                    )
                    print(
                        f"Applying {ema_source} EMA smoothing (alpha={section_ema_alpha}, "
                        f"{ema_interval_source} interval={section_ema_interval}s) to {section}"
                    )
                else:
                    print(
                        f"Applying {ema_source} EMA smoothing (alpha={section_ema_alpha}) to {section}"
                    )
                powermeter = ExponentialMovingAveragePowermeter(
                    powermeter, alpha=section_ema_alpha, ema_interval=section_ema_interval
                )

            section_slew_rate = safe_getfloat(
                config, section, "SLEW_RATE_WATTS_PER_SEC", fallback=global_slew_rate
            )
            if section_slew_rate > 0:
                slew_source = (
                    "section-specific"
                    if config.has_option(section, "SLEW_RATE_WATTS_PER_SEC")
                    else "global"
                )
                print(
                    f"Applying {slew_source} slew-rate limit ({section_slew_rate} W/s) to {section}"
                )
                powermeter = SlewRatePowermeter(powermeter, section_slew_rate)

            section_deadband_watts = safe_getfloat(
                config, section, "DEADBAND_WATTS", fallback=global_deadband_watts
            )
            if section_deadband_watts > 0:
                deadband_source = (
                    "section-specific"
                    if config.has_option(section, "DEADBAND_WATTS")
                    else "global"
                )
                print(
                    f"Applying {deadband_source} dead-band filter ({section_deadband_watts} W) to {section}"
                )
                powermeter = DeadBandPowermeter(powermeter, section_deadband_watts)

            section_hold_time = safe_getfloat(
                config, section, "HOLD_TIME", fallback=global_hold_time
            )
            if section_hold_time > 0:
                hold_source = (
                    "section-specific"
                    if config.has_option(section, "HOLD_TIME")
                    else "global"
                )
                print(
                    f"Applying {hold_source} hold timer ({section_hold_time}s) to {section}"
                )
                powermeter = HoldTimerPowermeter(powermeter, section_hold_time)

            section_power_offset = safe_getfloat(
                config, section, "POWER_OFFSET", fallback=global_power_offset
            )
            if section_power_offset != 0.0:
                offset_source = (
                    "section-specific"
                    if config.has_option(section, "POWER_OFFSET")
                    else "global"
                )
                print(
                    f"Applying {offset_source} power offset ({section_power_offset}W) to {section}"
                )
                powermeter = OffsetPowermeter(powermeter, offset=section_power_offset)

            client_filter = create_client_filter(section, config)
            powermeters.append((powermeter, client_filter))
    return powermeters


def create_client_filter(
    section: str, config: configparser.ConfigParser
) -> ClientFilter:
    netmasks = config.get(section, "NETMASK", fallback="0.0.0.0/0")
    netmasks = [IPv4Network(netmask) for netmask in netmasks.split(",")]
    return ClientFilter(netmasks)


# Helper function to create a powermeter instance
def create_powermeter(
    section: str, config: configparser.ConfigParser
) -> Union[Powermeter, None]:
    if section.startswith(SHELLY_SECTION):
        return create_shelly_powermeter(section, config)
    elif section.startswith(TASMOTA_SECTION):
        return create_tasmota_powermeter(section, config)
    elif section.startswith(SHRDZM_SECTION):
        return create_shrdzm_powermeter(section, config)
    elif section.startswith(EMLOG_SECTION):
        return create_emlog_powermeter(section, config)
    elif section.startswith(IOBROKER_SECTION):
        return create_iobroker_powermeter(section, config)
    elif section.startswith(HOMEASSISTANT_SECTION):
        return create_homeassistant_powermeter(section, config)
    elif section.startswith(VZLOGGER_SECTION):
        return create_vzlogger_powermeter(section, config)
    elif section.startswith(SCRIPT_SECTION):
        return create_script_powermeter(section, config)
    elif section.startswith(ESPHOME_SECTION):
        return create_esphome_powermeter(section, config)
    elif section.startswith(AMIS_READER_SECTION):
        return create_amisreader_powermeter(section, config)
    elif section.startswith(MODBUS_SECTION):
        return create_modbus_powermeter(section, config)
    elif section.startswith(TQ_EM_SECTION):
        return create_tq_em_powermeter(section, config)
    elif section.startswith(JSON_HTTP_SECTION):
        return create_json_http_powermeter(section, config)
    elif section.startswith("MQTT"):
        return create_mqtt_powermeter(section, config)
    else:
        return None


def create_shelly_powermeter(
    section: str, config: configparser.ConfigParser
) -> Powermeter:
    shelly_type = config.get(section, "TYPE", fallback="")
    shelly_ip = config.get(section, "IP", fallback="")
    shelly_user = config.get(section, "USER", fallback="")
    shelly_pass = config.get(section, "PASS", fallback="")
    shelly_meterindex = config.get(section, "METER_INDEX", fallback=None)
    if shelly_type == "1PM":
        return Shelly1PM(shelly_ip, shelly_user, shelly_pass, shelly_meterindex)
    elif shelly_type == "PLUS1PM":
        return ShellyPlus1PM(shelly_ip, shelly_user, shelly_pass, shelly_meterindex)
    elif shelly_type == "EM" or shelly_type == "3EM":
        return ShellyEM(shelly_ip, shelly_user, shelly_pass, shelly_meterindex)
    elif shelly_type == "3EMPro":
        return Shelly3EMPro(shelly_ip, shelly_user, shelly_pass, shelly_meterindex)
    else:
        raise Exception(f"Error: unknown Shelly type '{shelly_type}'")


def create_amisreader_powermeter(
    section: str, config: configparser.ConfigParser
) -> Powermeter:
    return AmisReader(config.get(section, "IP", fallback=""))


def create_script_powermeter(
    section: str, config: configparser.ConfigParser
) -> Powermeter:
    return Script(config.get(section, "COMMAND", fallback=""))


def create_mqtt_powermeter(
    section: str, config: configparser.ConfigParser
) -> Powermeter:
    return MqttPowermeter(
        config.get(section, "BROKER", fallback=""),
        safe_getint(config, section, "PORT", fallback=1883),
        config.get(section, "TOPIC", fallback=""),
        config.get(section, "JSON_PATH", fallback=None),
        config.get(section, "USERNAME", fallback=None),
        config.get(section, "PASSWORD", fallback=None),
    )


def create_json_http_powermeter(
    section: str, config: configparser.ConfigParser
) -> Powermeter:
    json_paths = config.get(section, "JSON_PATHS", fallback="").split(",")
    json_paths = [p.strip() for p in json_paths if p.strip()]
    json_path_value = json_paths[0] if len(json_paths) == 1 else json_paths
    return JsonHttpPowermeter(
        config.get(section, "URL", fallback=""),
        json_path_value,
        config.get(section, "USERNAME", fallback=None),
        config.get(section, "PASSWORD", fallback=None),
        (
            {
                k.strip(): v.strip()
                for k, v in (
                    [
                        item.split(":", 1)
                        for item in config.get(section, "HEADERS", fallback="").split(
                            ";"
                        )
                        if ":" in item
                    ]
                )
            }
            if config.get(section, "HEADERS", fallback="")
            else None
        ),
    )


def create_modbus_powermeter(
    section: str, config: configparser.ConfigParser
) -> Powermeter:
    return ModbusPowermeter(
        config.get(section, "HOST", fallback=""),
        safe_getint(config, section, "PORT", fallback=502),
        safe_getint(config, section, "UNIT_ID", fallback=1),
        safe_getint(config, section, "ADDRESS", fallback=0),
        safe_getint(config, section, "COUNT", fallback=1),
        config.get(section, "DATA_TYPE", fallback="UINT16"),
        config.get(section, "BYTE_ORDER", fallback="BIG"),
        config.get(section, "WORD_ORDER", fallback="BIG"),
        config.get(section, "REGISTER_TYPE", fallback="HOLDING"),
    )


def create_esphome_powermeter(
    section: str, config: configparser.ConfigParser
) -> Powermeter:
    return ESPHome(
        config.get(section, "IP", fallback=""),
        config.get(section, "PORT", fallback=""),
        config.get(section, "DOMAIN", fallback=""),
        config.get(section, "ID", fallback=""),
    )


def create_vzlogger_powermeter(
    section: str, config: configparser.ConfigParser
) -> Powermeter:
    return VZLogger(
        config.get(section, "IP", fallback=""),
        config.get(section, "PORT", fallback=""),
        config.get(section, "UUID", fallback=""),
    )


def create_homeassistant_powermeter(
    section: str, config: configparser.ConfigParser
) -> Powermeter:
    # Split entity strings on commas and strip whitespace
    def parse_entities(value: str) -> Union[str, List[str]]:
        if not value:
            return ""
        entities = [entity.strip() for entity in value.split(",")]
        # Return single string if only one entity, otherwise return list
        return entities[0] if len(entities) == 1 else entities

    current_power_entity = parse_entities(
        config.get(section, "CURRENT_POWER_ENTITY", fallback="")
    )
    power_input_alias = parse_entities(
        config.get(section, "POWER_INPUT_ALIAS", fallback="")
    )
    power_output_alias = parse_entities(
        config.get(section, "POWER_OUTPUT_ALIAS", fallback="")
    )

    return HomeAssistant(
        config.get(section, "IP", fallback=""),
        config.get(section, "PORT", fallback=""),
        safe_getboolean(config, section, "HTTPS", fallback=False),
        config.get(section, "ACCESSTOKEN", fallback=""),
        current_power_entity,
        safe_getboolean(config, section, "POWER_CALCULATE", fallback=False),
        power_input_alias,
        power_output_alias,
        config.get(section, "API_PATH_PREFIX", fallback=None),
    )


def create_iobroker_powermeter(
    section: str, config: configparser.ConfigParser
) -> Powermeter:
    return IoBroker(
        config.get(section, "IP", fallback=""),
        config.get(section, "PORT", fallback=""),
        config.get(section, "CURRENT_POWER_ALIAS", fallback=""),
        safe_getboolean(config, section, "POWER_CALCULATE", fallback=False),
        config.get(section, "POWER_INPUT_ALIAS", fallback=""),
        config.get(section, "POWER_OUTPUT_ALIAS", fallback=""),
    )


def create_emlog_powermeter(
    section: str, config: configparser.ConfigParser
) -> Powermeter:
    return Emlog(
        config.get(section, "IP", fallback=""),
        config.get(section, "METER_INDEX", fallback=""),
        safe_getboolean(config, section, "JSON_POWER_CALCULATE", fallback=False),
    )


def create_shrdzm_powermeter(
    section: str, config: configparser.ConfigParser
) -> Powermeter:
    return Shrdzm(
        config.get(section, "IP", fallback=""),
        config.get(section, "USER", fallback=""),
        config.get(section, "PASS", fallback=""),
    )


def create_tasmota_powermeter(
    section: str, config: configparser.ConfigParser
) -> Powermeter:
    return Tasmota(
        config.get(section, "IP", fallback=""),
        config.get(section, "USER", fallback=""),
        config.get(section, "PASS", fallback=""),
        config.get(section, "JSON_STATUS", fallback=""),
        config.get(section, "JSON_PAYLOAD_MQTT_PREFIX", fallback=""),
        config.get(section, "JSON_POWER_MQTT_LABEL", fallback=""),
        config.get(section, "JSON_POWER_INPUT_MQTT_LABEL", fallback=""),
        config.get(section, "JSON_POWER_OUTPUT_MQTT_LABEL", fallback=""),
        safe_getboolean(config, section, "JSON_POWER_CALCULATE", fallback=False),
    )


def create_tq_em_powermeter(
    section: str, config: configparser.ConfigParser
) -> Powermeter:
    return TQEnergyManager(
        config.get(section, "IP", fallback=""),
        config.get(section, "PASSWORD", fallback=""),
        timeout=safe_getfloat(config, section, "TIMEOUT", fallback=5.0),
    )
