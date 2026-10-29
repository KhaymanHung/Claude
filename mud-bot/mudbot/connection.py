"""Telnet 連線：處理 telnet 協定位元組、Big5 編碼與 ANSI 色碼。"""

import asyncio
import codecs
import datetime as dt
import re
from pathlib import Path

IAC, DONT, DO, WONT, WILL, SB, SE = 255, 254, 253, 252, 251, 250, 240
GA = 249

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


class ColorSplitFixer:
    """有些房間名稱和物品是「每個位元組各上一個顏色」，色碼夾在中文字的兩個位元組中間，
    直接解碼會變亂碼（例如「聊天室」變成「������」）。這裡把夾在中間的色碼移到那個字的後面。
    可以跨封包：沒處理完的尾巴留到下一包。"""

    def __init__(self):
        self.carry = b""

    def feed(self, data: bytes) -> bytes:
        buf, self.carry = self.carry + data, b""
        out, held = bytearray(), bytearray()
        lead_at = -1                       # 等待第二個位元組的中文字首（在 buf 裡的位置）
        i, n = 0, len(buf)
        while i < n:
            b = buf[i]
            if b == 0x1B:
                if i + 1 >= n:
                    return self._stop(buf, out, held, lead_at, i)
                if buf[i + 1] == 0x5B:     # ESC [
                    j = i + 2
                    while j < n and not (0x40 <= buf[j] <= 0x7E):
                        j += 1
                    if j >= n:
                        return self._stop(buf, out, held, lead_at, i)
                    (held if lead_at >= 0 else out).extend(buf[i:j + 1])
                    i = j + 1
                    continue
            if lead_at >= 0:
                if 0x40 <= b <= 0x7E or 0xA1 <= b <= 0xFE:   # Big5 第二個位元組
                    out.append(b)
                    out.extend(held)
                    held.clear()
                    lead_at = -1
                    i += 1
                    continue
                out.extend(held)           # 不成對：照原樣
                held.clear()
                lead_at = -1
            if 0x81 <= b <= 0xFE:
                lead_at = i
            out.append(b)
            i += 1
        if lead_at >= 0:                   # 字首後面斷包了：字首和色碼一起留到下一包
            del out[-1]
            self.carry = bytes([buf[lead_at]]) + bytes(held)
        return bytes(out)

    def _stop(self, buf, out, held, lead_at, i):
        if lead_at >= 0:
            del out[-1]
            self.carry = bytes([buf[lead_at]]) + bytes(held) + buf[i:]
        else:
            self.carry = buf[i:]
        return bytes(out)


class MudConnection:
    def __init__(self, host: str, port: int, encoding: str = "cp950", raw_log: Path | None = None):
        self.host = host
        self.port = port
        self.encoding = encoding
        self._decoder = codecs.getincrementaldecoder(encoding)(errors="replace")
        self._pending = b""                    # 被切在兩個封包之間的 telnet 指令
        self._fixer = ColorSplitFixer()        # 修正色碼夾在中文字中間造成的亂碼
        # 原始封包紀錄：每一包收到（<<）和送出（>>）的資料，保留顏色碼、telnet 指令和無法解碼的位元組
        self.raw = open(raw_log, "a", encoding="utf-8") if raw_log else None
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None

    async def connect(self) -> None:
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)

    @property
    def connected(self) -> bool:
        return self.writer is not None and not self.writer.is_closing()

    async def read(self) -> str | None:
        """讀一批資料並回傳解碼後的文字；連線中斷時回傳 None。"""
        data = await self.reader.read(4096)
        if not data:
            self._log_raw("<<", b"", note="伺服器斷線")
            return None
        self._log_raw("<<", data)
        data, self._pending = self._pending + data, b""
        return self._decoder.decode(self._fixer.feed(self._handle_telnet(data)))

    def _log_raw(self, direction: str, data: bytes, note: str = "") -> None:
        """寫入原始封包紀錄。可見文字照原樣，控制字元和無法解碼的位元組寫成 \\xNN。"""
        if not self.raw:
            return
        text = data.decode(self.encoding, errors="backslashreplace")
        text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", lambda m: f"\\x{ord(m.group()):02x}", text)
        text = text.replace("\r", "\\r").replace("\n", "\\n\n    ")
        stamp = dt.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.raw.write(f"{stamp} {direction} {len(data)}B {note}| {text}\n")
        self.raw.flush()

    def _handle_telnet(self, data: bytes) -> bytes:
        """移除 telnet 協商位元組，並一律拒絕伺服器要求的選項。"""
        out = bytearray()
        i = 0
        while i < len(data):
            b = data[i]
            if b != IAC:
                out.append(b)
                i += 1
                continue
            if i + 1 >= len(data) or (data[i + 1] in (DO, DONT, WILL, WONT) and i + 2 >= len(data)):
                self._pending = data[i:]            # telnet 指令被切開，留到下一包再處理
                break
            cmd = data[i + 1]
            if cmd == IAC:                      # 跳脫的 0xFF
                out.append(IAC)
                i += 2
            elif cmd in (DO, DONT, WILL, WONT) and i + 2 < len(data):
                opt = data[i + 2]
                if cmd == DO:
                    self._raw_send(bytes([IAC, WONT, opt]))
                elif cmd == WILL:
                    self._raw_send(bytes([IAC, DONT, opt]))
                i += 3
            elif cmd == SB:                     # 子協商：略過到 IAC SE
                end = data.find(bytes([IAC, SE]), i)
                if end == -1:
                    self._pending = data[i:]
                    break
                i = end + 2
            else:                               # GA 等單一指令
                i += 2
        return bytes(out)

    def _raw_send(self, data: bytes, secret: bool = False) -> None:
        if self.connected:
            self._log_raw(">>", b"********\r\n" if secret else data, note="（密碼）" if secret else "")
            self.writer.write(data)

    async def send(self, line: str, secret: bool = False) -> None:
        payload = line.encode(self.encoding, errors="replace")
        payload = payload.replace(bytes([IAC]), bytes([IAC, IAC]))
        self._raw_send(payload + b"\r\n", secret)
        await self.writer.drain()

    async def close(self) -> None:
        if self.raw:
            self.raw.flush()
        if self.connected:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except Exception:
                pass
