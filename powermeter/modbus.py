import struct

from .base import Powermeter
from pymodbus.client import ModbusTcpClient


STRUCT_FORMATS = {
    "FLOAT32": "f",
    "INT16": "h",
    "UINT16": "H",
    "INT32": "i",
    "UINT32": "I",
}


REGISTER_TYPES = {
    "HOLDING": "read_holding_registers",
    "INPUT": "read_input_registers",
}


class ModbusPowermeter(Powermeter):
    def __init__(
        self,
        host,
        port,
        unit_id,
        address,
        count,
        data_type="UINT16",
        byte_order="BIG",
        word_order="BIG",
        register_type="HOLDING",
    ):
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.address = address
        self.count = count
        self.data_type = data_type.upper()
        self.byte_order = byte_order.upper()
        self.word_order = word_order.upper()

        if self.data_type not in STRUCT_FORMATS:
            raise ValueError(f"Unsupported data type: {data_type}")

        self.register_type = register_type.upper()
        self._read_method = REGISTER_TYPES.get(self.register_type)
        if not self._read_method:
            raise ValueError(f"Unsupported register type: {register_type}")

        self.client = ModbusTcpClient(host, port=port)

    def get_powermeter_watts(self):
        read = getattr(self.client, self._read_method)
        result = read(self.address, self.count, slave=self.unit_id)
        if result.isError():
            raise Exception("Error reading Modbus data")
        bo = ">" if self.byte_order == "BIG" else "<"
        word_bytes = [struct.pack(f"{bo}H", r) for r in result.registers]
        if self.word_order == "LITTLE":
            word_bytes = list(reversed(word_bytes))
        raw = b"".join(word_bytes)
        fmt_char = STRUCT_FORMATS[self.data_type]
        value = struct.unpack(f"{bo}{fmt_char}", raw)[0]
        return [float(value)]
