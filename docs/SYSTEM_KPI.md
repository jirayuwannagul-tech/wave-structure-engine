# System KPI

เอกสารนี้ใช้เป็นกรอบวัดผลระบบใน local สำหรับงานพัฒนา ไม่ได้ผูกกับ VPS โดยตรง

## เป้าหมาย

วัด 3 ส่วนของระบบให้เป็นตัวเลขเดียวกันทุกครั้งที่เราปรับ logic

1. Data ingestion
2. Wave counting
3. Entry pipeline
4. Profitability gate

## คำสั่ง

```bash
python main.py system-kpi --symbols BTCUSDT ETHUSDT BNBUSDT SOLUSDT DOGEUSDT
```

ค่า default:

- `analysis_timeframes = 1D 4H`
- `data_timeframes = 1W 1D 4H`
- output ถูกเขียนที่ `storage/local_system_kpi_report.json`

## Metric หลัก

### 1. Data

- `dataset_coverage_pct`
  วัดว่าชุดข้อมูลแท่งที่ต้องใช้มีไฟล์และไม่ว่าง

### 2. Wave Counting

- `weekly_validation_accuracy_pct`
  ใช้ ground-truth benchmark ใน `tests/wave_validation_labels.py`
- `position_resolution_pct`
  วัดว่า 1D/4H resolve wave position ได้ ไม่เป็น `UNKNOWN`
- `structure_retention_pct`
  วัดว่า pattern subtype เช่น triangle/flat ยังถูกส่งต่อถึง position
- `projection_resolution_pct`
  วัดว่า projection layer ไม่ตก `UNKNOWN`

### 3. Entry Pipeline

- `scenario_coverage_pct`
  วัดว่า analysis ออก scenario ได้หรือไม่
- `actionable_entry_pct`
  วัดว่า scenario มี `entry + stop + targets` ครบหรือไม่
- `valid_entry_geometry_pct`
  วัดว่า geometry ถูกด้าน
  - bullish: `SL < entry < targets`
  - bearish: `targets < entry < SL`

### 4. Profitability

- `profitable_backtest_pct`
  วัดว่า backtest ราย symbol/timeframe มีกำไรจริงกี่ %
- `positive_expectancy_pct`
  วัดว่า backtest ราย symbol/timeframe มี `avg_r_per_trade > 0` กี่ %

## เกณฑ์ผ่านใหม่

ระบบจะยังไม่ถือว่า "ผ่าน" ตาม KPI ใหม่ ถ้า profitability ยังไม่ถึงเกณฑ์

- `minimum pass = 70%`
- `strong pass = 80%`

ค่าเหล่านี้จะถูกแสดงใน `profitability_gate`

## การตีความ

- `section_scores.data`
  ใช้ดูความพร้อมของข้อมูลต้นทาง
- `section_scores.wave_counting`
  ใช้ดูว่าระบบนับคลื่นได้มั่นคงแค่ไหน
- `section_scores.entry_pipeline`
  ใช้ดูว่าระบบแปลงคลื่นเป็น entry ได้สมเหตุสมผลแค่ไหน
- `section_scores.profitability`
  ใช้ดูว่าระบบทำกำไรได้จริงแค่ไหนบน backtest ปัจจุบัน

คะแนนพวกนี้เป็น KPI ภายในทีม ใช้เทียบก่อน/หลังการแก้ logic
