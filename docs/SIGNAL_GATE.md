# Signal gate (ไม่ซ้ำ entry / รอจบที่ SL หรือ TP3)

เมื่อเปิด `SIGNAL_GATE_TERMINAL_EXIT=true` ระบบจะ**ไม่สร้างแถวสัญญาณใหม่**ใน DB (และจึงไม่ push แผนใหม่ไป Sheet/Telegram ตาม flow เดิม) ถ้ายังมีสัญญาณสถานะเปิดอยู่:

- `PENDING_ENTRY`, `ACTIVE`, `PARTIAL_TP1`, `PARTIAL_TP2`

จนกว่าสัญญาณนั้นจะปิดด้วย **TP3** (`TP3_HIT`) หรือ **SL** (`STOPPED`) — หรือสถานะอื่นที่ไม่ใช่ “เปิด” เช่น `INVALIDATED` (ยกเลิกก่อนเข้า), `REPLACED` (โหมดเก่า)

## พฤติกรรมเมื่อเปิด gate

มีได้ **สัญญาณเปิดทีละ 1 ต่อ symbol** (ทุก timeframe) จนกว่าจะปิดที่ **SL/TP3**

## ตั้งค่าใน `.env`

```env
SIGNAL_GATE_TERMINAL_EXIT=true
```

ถ้าไม่ตั้งหรือเป็น `false` พฤติกรรมเดิมยังใช้ได้ (แทนที่ PENDING ด้วยแผนใหม่ได้)
