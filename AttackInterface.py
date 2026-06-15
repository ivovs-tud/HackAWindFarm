"""
Python implementation of the C++ AttackInterface protocol.

Provides binary-compatible pack/unpack for all message structs so that
data can be exchanged with the C++ side over ZeroMQ using the same raw-byte format.

Assumed struct layout: standard x86-64 GCC, little-endian, no packing pragmas.
  - C++ unscoped enums compiled as uint32_t (4 bytes)
  - uint64_t (TimeStamp) aligned to 8 bytes
  - Struct members naturally aligned

If the C++ side uses __attribute__((packed)) or #pragma pack(1), adjust the
format strings by removing the padding ('x') characters.
"""

import struct
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import List
import threading
import zmq
import logging

logging.basicConfig(level=logging.WARNING)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DataHeader(IntEnum):
    TX_DATA = 0x01   # Data just for transmission
    RQ_DATA = 0x02   # Request for sending specific data
    AT_DATA = 0x04   # Data containing overwrite signals (response to RQ_DATA)
    CT_DATA = 0x08   # Control data
    CFG_DATA = 0x10  # Configuration data
    SIM_CTRL = 0x20  # Simulation control data


class TxDataType(IntEnum):
    TX_WS      = 0x01   # Wind Speed
    TX_WD      = 0x02   # Wind Direction
    TX_ST      = 0x03   # Turbine Status
    TX_PW      = 0x04   # Power generation
    TX_YAW     = 0x05   # Yaw angle
    TX_RPM     = 0x06   # Rotor speed
    TX_PTCH    = 0x07   # Pitch angle
    TX_SPT_YAW = 0x08   # Yaw setpoint
    TX_SPT_PWR = 0x09   # Power setpoint
    TX_GEN_TORQ= 0x10   # Generator torque
    TX_ARRAY   = 0xFF   # Extensibility placeholder


class ControlSignal(IntEnum):
    CTRL_NONE = 0x00   # Nothing
    CTRL_TAP  = 0x01   # Start/stop tapping communication
    CTRL_FDI  = 0x02   # Start/stop false data injection attack


# ---------------------------------------------------------------------------
# Struct format strings (little-endian '<')
#
#  TxDataMessage  — 16 bytes
#    offset  0 : uint8_t  header          [1B]
#    offset  1 : uint8_t  turbineId       [1B]
#    offset 2-3: padding                  [2B]
#    offset  4 : uint32_t dataType (enum) [4B]
#    offset  8 : uint8_t  payload_length  [1B]
#    offset 9-11: padding                 [3B]
#    offset 12 : float    value           [4B]
#
#  RqDataMessage — 24 bytes
#    offset  0 : uint8_t  header          [1B]
#    offset  1 : uint8_t  turbineId       [1B]
#    offset 2-3: padding                  [2B]
#    offset  4 : uint32_t dataType (enum) [4B]
#    offset  8 : uint64_t rq_time         [8B]
#    offset 16 : uint64_t exp_time        [8B]
#
#  AtDataMessage — 24 bytes
#    offset  0 : uint8_t  header          [1B]
#    offset  1 : uint8_t  turbineId       [1B]
#    offset 2-3: padding                  [2B]
#    offset  4 : uint32_t dataType (enum) [4B]
#    offset  8 : uint64_t at_time         [8B]
#    offset 16 : float    fake_value      [4B]
#    offset 20-23: padding                [4B]  (struct aligned to 8)
#
#  CtDataMessage — variable length
#    offset  0 : uint8_t  header          [1B]
#    offset 1-3: padding                  [3B]
#    offset  4 : uint32_t signal (enum)   [4B]
#    offset  8 : uint32_t dataType (enum) [4B]
#    offset 12 : uint8_t  enable[n]       [1B each]  (length inferred from message size)
#
#  CfgDataMessage — 268 bytes
#    offset  0 : uint8_t  header            [1B]
#    offset 1-256: char     teamName[256]   [256B]
#    offset 257-259: padding                [3B]
#    offset 260 : int32_t  scenarioId       [4B]
#    offset 264 : int32_t  turbineController[4B]
#
#  SimCtrlMessage — 2 bytes
#    offset  0 : uint8_t  header          [1B]
#    offset  1 : uint8_t  simStart        [1B]
# ---------------------------------------------------------------------------

_FMT_TX      = struct.Struct('<BB2xIB3xf')  # 16 bytes
_FMT_RQ      = struct.Struct('<BB2xIQQ')    # 24 bytes
_FMT_AT      = struct.Struct('<BB2xIQf4x')  # 24 bytes
_FMT_CT_HDR  = struct.Struct('<B3xII')      # 12 bytes  (header + signal + dataType)
_FMT_CFG     = struct.Struct('<B256s3xii')  # 268 bytes
_FMT_SIMCTRL = struct.Struct('<BB')         # 2 bytes


# ---------------------------------------------------------------------------
# Message dataclasses
# ---------------------------------------------------------------------------

@dataclass
class TxDataMessage:
    turbine_id:     int
    data_type:      TxDataType
    value:          float
    header:         int = DataHeader.TX_DATA
    payload_length: int = 0x01

    def pack(self) -> bytes:
        return _FMT_TX.pack(self.header, self.turbine_id, int(self.data_type), self.payload_length, self.value)

    @classmethod
    def unpack(cls, data: bytes) -> "TxDataMessage":
        header, turbine_id, data_type, payload_length, value = _FMT_TX.unpack(data)
        return cls(turbine_id=turbine_id, data_type=TxDataType(data_type), value=value, header=header, payload_length=payload_length)


@dataclass
class RqDataMessage:
    turbine_id: int
    data_type:  TxDataType
    rq_time:    int   # Unix timestamp in milliseconds
    exp_time:   int   # Expiry timestamp in milliseconds
    header:     int = DataHeader.RQ_DATA

    def pack(self) -> bytes:
        return _FMT_RQ.pack(self.header, self.turbine_id, int(self.data_type), self.rq_time, self.exp_time)

    @classmethod
    def unpack(cls, data: bytes) -> "RqDataMessage":
        header, turbine_id, data_type, rq_time, exp_time = _FMT_RQ.unpack(data)
        return cls(turbine_id=turbine_id, data_type=TxDataType(data_type), rq_time=rq_time, exp_time=exp_time, header=header)


@dataclass
class AtDataMessage:
    turbine_id: int
    data_type:  TxDataType
    at_time:    int   # Unix timestamp in milliseconds
    fake_value: float
    header:     int = DataHeader.AT_DATA

    def pack(self) -> bytes:
        return _FMT_AT.pack(self.header, self.turbine_id, int(self.data_type), self.at_time, self.fake_value)

    @classmethod
    def unpack(cls, data: bytes) -> "AtDataMessage":
        header, turbine_id, data_type, at_time, fake_value = _FMT_AT.unpack(data)
        return cls(turbine_id=turbine_id, data_type=TxDataType(data_type), at_time=at_time, fake_value=fake_value, header=header)


@dataclass
class CtDataMessage:
    signal:    ControlSignal
    data_type: TxDataType
    enable:    List[bool]          # per-turbine enable flags (0 or 1), 1-based index
    header:    int = DataHeader.CT_DATA

    def pack(self) -> bytes:
        hdr     = _FMT_CT_HDR.pack(self.header, int(self.signal), int(self.data_type))
        payload = struct.pack(f'<{len(self.enable)}B', *self.enable)
        return hdr + payload

    @classmethod
    def unpack(cls, data: bytes) -> "CtDataMessage":
        header, signal, data_type = _FMT_CT_HDR.unpack(data[:_FMT_CT_HDR.size])
        count = len(data) - _FMT_CT_HDR.size
        enable = list(struct.unpack_from(f'<{count}B', data, _FMT_CT_HDR.size))
        return cls(signal=ControlSignal(signal), data_type=TxDataType(data_type), enable=enable, header=header)


@dataclass
class CfgDataMessage:
    team_name: str
    scenario_id: int
    turbine_controller: int
    header: int = DataHeader.CFG_DATA

    def pack(self) -> bytes:
        encoded_name = self.team_name.encode('utf-8')[:255]
        team_name = encoded_name + b'\x00' * (256 - len(encoded_name))
        return _FMT_CFG.pack(self.header, team_name, self.scenario_id, self.turbine_controller)

    @classmethod
    def unpack(cls, data: bytes) -> "CfgDataMessage":
        header, team_name, scenario_id, turbine_controller = _FMT_CFG.unpack(data)
        decoded_name = team_name.split(b'\x00', 1)[0].decode('utf-8', errors='ignore')
        return cls(team_name=decoded_name, scenario_id=scenario_id, turbine_controller=turbine_controller, header=header)


@dataclass
class SimCtrlMessage:
    sim_start: bool
    header: int = DataHeader.SIM_CTRL

    def pack(self) -> bytes:
        return _FMT_SIMCTRL.pack(self.header, int(self.sim_start))

    @classmethod
    def unpack(cls, data: bytes) -> "SimCtrlMessage":
        header, sim_start = _FMT_SIMCTRL.unpack(data)
        return cls(sim_start=bool(sim_start), header=header)


# ---------------------------------------------------------------------------
# Dispatcher: parse raw bytes into the correct message type
# ---------------------------------------------------------------------------

def parse_message(data: bytes):
    """Inspect the header byte and deserialize into the correct message type."""
    if not data:
        logging.warning("Received empty message")
        return None
        # raise ValueError("Empty message")
    header = data[0]
    if header == DataHeader.TX_DATA:
        return TxDataMessage.unpack(data)
    elif header == DataHeader.RQ_DATA:
        return RqDataMessage.unpack(data)
    elif header == DataHeader.AT_DATA:
        return AtDataMessage.unpack(data)
    elif header == DataHeader.CT_DATA:
        return CtDataMessage.unpack(data)
    elif header == DataHeader.CFG_DATA:
        return CfgDataMessage.unpack(data)
    elif header == DataHeader.SIM_CTRL:
        return SimCtrlMessage.unpack(data)
    else:
        logging.warning(f"Received unknown header byte: 0x{header:02X}")
        return None
        # raise ValueError(f"Unknown header byte: 0x{header:02X}")


# ---------------------------------------------------------------------------
# AttackInterface class  (mirrors the C++ AttackInterface)
# ---------------------------------------------------------------------------

class AttackProtocolInterface:
    """
    Python equivalent of the C++ AttackInterface class.

    Tracks per-turbine control state and handles ZeroMQ send/receive
    using the binary protocol defined above.
    """

    # Default control-enable state matches the C++ constructor
    _DEFAULT_CONTROL: dict = {
        TxDataType.TX_WS:      True,
        TxDataType.TX_WD:      True,
        TxDataType.TX_ST:      False,
        TxDataType.TX_PW:      False,
        TxDataType.TX_YAW:     False,
        TxDataType.TX_RPM:     False,
        TxDataType.TX_PTCH:    False,
        TxDataType.TX_SPT_YAW: False,
        TxDataType.TX_SPT_PWR: False,
        TxDataType.TX_GEN_TORQ: False,
    }

    def __init__(self, num_turbines: int, socket: zmq.Socket):
        self._socket = socket
        # Index 0 = turbine 1 (1-based, matching C++)
        self._link_states: list[dict[TxDataType, bool]] = [
            dict(self._DEFAULT_CONTROL) for _ in range(num_turbines)
        ]

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    def tx_data(self, turbine_id: int, data_type: TxDataType, value: float) -> None:
        """Send a TxDataMessage if control is enabled for this turbine/type."""
        if not self._valid_turbine(turbine_id):
            return
        
        logging.debug(f"tx_data  turbine={turbine_id}  type={data_type.name}  value={value}")
        

        if self._link_states[turbine_id - 1].get(data_type, False):
            msg = TxDataMessage(turbine_id=turbine_id, data_type=data_type, value=value)
            self._socket.send(msg.pack())

    def send_request(self, turbine_id: int, data_type: TxDataType, ttl_ms: int = 5000) -> None:
        """Send an RqDataMessage requesting a specific data type from a turbine."""
        if not self._valid_turbine(turbine_id):
            return
        
        now = int(time.time() * 1000)
        msg = RqDataMessage(turbine_id=turbine_id, data_type=data_type, rq_time=now, exp_time=now + ttl_ms)
        logging.debug(f"send_request  turbine={turbine_id}  type={data_type.name}")
        self._socket.send(msg.pack())

    def send_attack(self, turbine_id: int, data_type: TxDataType, fake_value: float, at_time_ms: int | None = None) -> None:
        """Send an AtDataMessage (false data injection payload)."""
        if not self._valid_turbine(turbine_id):
            return
        
        if at_time_ms is None:
            at_time_ms = int(time.time() * 1000)

        msg = AtDataMessage(turbine_id=turbine_id, data_type=data_type, at_time=at_time_ms, fake_value=fake_value)
        logging.debug(f"send_attack  turbine={turbine_id}  type={data_type.name}  fake={fake_value}")
        self._socket.send(msg.pack())

    def send_control(self, signal: ControlSignal, data_type: TxDataType, enable: list[int]) -> None:
        """Send a CtDataMessage (control signal for all turbines)."""
        msg = CtDataMessage(signal=signal, data_type=data_type, enable=enable)
        logging.debug(f"send_control  signal={signal.name}  type={data_type.name}  enable={enable}")
        self._socket.send(msg.pack())

    def send_config(self, team_name: str, scenario_id: int, turbine_controller: int) -> None:
        """Send a CfgDataMessage with the current simulation configuration."""
        msg = CfgDataMessage(team_name=team_name, scenario_id=scenario_id, turbine_controller=turbine_controller)
        logging.debug(f"send_config  team={team_name!r}  scenario={scenario_id}  controller={turbine_controller}")
        self._socket.send(msg.pack())

    def send_sim_control(self, sim_start: bool) -> None:
        """Send a SimCtrlMessage to toggle simulation readiness/start."""
        msg = SimCtrlMessage(sim_start=sim_start)
        logging.debug(f"send_sim_control  sim_start={sim_start}")
        self._socket.send(msg.pack())

    # ------------------------------------------------------------------
    # Receiving
    # ------------------------------------------------------------------

    def recv_message(self):
        """Block until a message arrives, print raw bytes, and return parsed object."""
        try:
            raw = self._socket.recv()
        except zmq.Again:
            return None

        logging.debug(f"Received raw bytes: {raw}")
        return parse_message(raw)

    def wait_for_ready(self) -> SimCtrlMessage:
        """Block until a ready SimCtrlMessage is received and return it."""
        while True:
            message = self.recv_message()
            if message is None:
                continue
            if isinstance(message, SimCtrlMessage) and message.sim_start:
                logging.debug("Received ready message")
                return message

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def set_control(self, turbine_id: int, data_type: TxDataType, enabled: bool) -> None:
        """Enable or disable attack-interface control for a turbine/data-type pair."""
        if not self._valid_turbine(turbine_id):
            return
        
        self._link_states[turbine_id - 1][data_type] = enabled

    def is_controlled(self, turbine_id: int, data_type: TxDataType) -> bool:
        if not self._valid_turbine(turbine_id):
            return False
        
        return self._link_states[turbine_id - 1].get(data_type, False)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _valid_turbine(self, turbine_id: int) -> bool:
        if turbine_id < 1 or turbine_id > len(self._link_states):
            logging.warning(f"Invalid turbine ID: {turbine_id}")
            return False
        return True

# ------------------------------------------------------------------
# Actual Interface As Used by Participants
# ------------------------------------------------------------------

class AttackInterface:

    server_ip = None
    port = None
    INTERVAL_SECONDS = 0.01         # Task Time for Receiving
    ATTACK_INTERVAL_SECONDS = 0.1   # Task Time for Attack Function
    ZEROMQ_MAX_MESSAGES = 10
    RECV_TIMEOUT_MS = 500
    SEND_TIMEOUT_MS = 500

    _TEXT2TYPE = {
        'Wind Speed':       TxDataType.TX_WS,
        'Wind Direction':   TxDataType.TX_WD,
        'Rotor Speed':      TxDataType.TX_RPM,
        'Yaw':              TxDataType.TX_YAW,
        'Blade Pitch':      TxDataType.TX_PTCH,
        'Power':            TxDataType.TX_PW,
        'Yaw Setpoint':     TxDataType.TX_SPT_YAW,
        'Power Setpoint':   TxDataType.TX_SPT_PWR,
        'Generator Torque': TxDataType.TX_GEN_TORQ
    }

    _TYPE2TEXT = {v: k for k, v in _TEXT2TYPE.items()}

    class _AttackInterfaceExcept(Exception): pass

    def __init__(self, num_turbines: int = 9):
        self.num_turbines = num_turbines
        self._context  = zmq.Context()
        self._socket = self._context.socket(zmq.PAIR)

        self._socket.setsockopt(zmq.SNDHWM, self.ZEROMQ_MAX_MESSAGES)
        self._socket.setsockopt(zmq.RCVTIMEO, self.RECV_TIMEOUT_MS)
        self._socket.setsockopt(zmq.SNDTIMEO, self.SEND_TIMEOUT_MS)

        self._protocol_interface = AttackProtocolInterface(self.num_turbines, self._socket)

        self._tap_cfg = {key : [False * self.num_turbines] for key in self._TEXT2TYPE.keys()}
        self._fdi_cfg = {key : [False * self.num_turbines] for key in self._TEXT2TYPE.keys()}
        self.last_received = {key : [float('nan')] * self.num_turbines for key in self._TEXT2TYPE.keys()}
        self.fdi_next = {key : [float('nan')] * self.num_turbines for key in self._TEXT2TYPE.keys()}

        self._attack_func = None


    def connect(self, server_ip: str, port: int):
        self.server_ip = server_ip
        self.port = port

        self._socket.connect(f"tcp://{server_ip}:{port}")
        print(f"Connected to {server_ip}:{port}")
    
    def configure(self, team_name: str):
        self.team_name = team_name
        self.scenario_id = 0
        self.turbine_controller = 0

        self._protocol_interface.send_config(team_name=self.team_name, scenario_id=self.scenario_id, turbine_controller=self.turbine_controller)  

    def tap_communication(self, channels, turbine_ids):
        if not type(turbine_ids) == list or len(turbine_ids) != self.num_turbines:
            raise self._AttackInterfaceExcept(f"turbine_ids must be a list of length {self.num_turbines}")
        
        if not type(channels) == list:
            channels = [channels]
        
        for c in channels:
            self._tap_cfg[c][0] = turbine_ids
            self._protocol_interface.send_control(ControlSignal.CTRL_TAP, self._TEXT2TYPE[c], enable=turbine_ids)

    def fdi_communication(self, channels, turbine_ids):
        if not type(turbine_ids) == list or len(turbine_ids) != self.num_turbines:
            raise self._AttackInterfaceExcept(f"turbine_ids must be a list of length {self.num_turbines}")
        
        if not type(channels) == list:
            channels = [channels]
        
        for c in channels:
            self._fdi_cfg[c][0] = turbine_ids
            self._protocol_interface.send_control(ControlSignal.CTRL_FDI, self._TEXT2TYPE[c], enable=turbine_ids)

    def start(self, attack_func):
        self._attack_func = attack_func
        self._protocol_interface.send_sim_control(sim_start=True)
        self._protocol_interface.wait_for_ready()

        attack_thread = threading.Thread(target=self._attack_loop, daemon=True)
        attack_thread.start()

        print("Attack Interface Started!")

        while True:
            self._execute()
            time.sleep(self.INTERVAL_SECONDS)

    def _attack_loop(self):
        start_time_ms = time.time_ns() // 1_000_000
        time_ms = lambda: time.time_ns() // 1_000_000 - start_time_ms
        while True:
            self._attack_func(self.last_received, self.fdi_next, time_ms())
            time.sleep(self.ATTACK_INTERVAL_SECONDS)

    def stop(self):
        self._socket.close()
        self._context.term()

    def _handle_rq_data(self, msg):
        if time.time_ns() // 1_000_000 > msg.exp_time:
            return
        
        if msg.data_type not in self._TYPE2TEXT:
            return
        
        val = self.fdi_next[self._TYPE2TEXT[msg.data_type]][msg.turbine_id - 1]
        self._protocol_interface.send_attack(msg.turbine_id, msg.data_type, val, time.time_ns() // 1_000_000)
        logging.debug(f"Received request for data. Turbine ID: {msg.turbine_id}, Data Type: {self._TYPE2TEXT[msg.data_type]}. Wrote {val}")

    def _handle_tx_data(self, msg):
        if msg.data_type not in self._TYPE2TEXT:
            return

        self.last_received[self._TYPE2TEXT[msg.data_type]][msg.turbine_id-1] = msg.value

    def _execute(self):
        try:
            raw = self._socket.recv()
        except zmq.Again:
            return
        msg = parse_message(raw)
        match msg.header:
            case DataHeader.RQ_DATA:
                self._handle_rq_data(msg)                

            case DataHeader.TX_DATA:
                self._handle_tx_data(msg)

            case DataHeader.CFG_DATA:
                logging.debug(f"Received configuration message. Team: {msg.team_name}")

            case DataHeader.SIM_CTRL:
                logging.debug(f"Received simulation control message. sim_start={msg.sim_start}")

            case _:
                raise self._AttackInterfaceExcept()
