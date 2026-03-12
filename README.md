# Elliott Wave Engine

## Project Objective

โปรเจกต์นี้มีเป้าหมายเดียวคือ

สร้างระบบที่สามารถ **นับ Elliott Wave ตามกฎให้ถูกต้องที่สุด**  
และ **สร้าง Scenario จากโครงสร้างคลื่นนั้น**

ระบบนี้ **ไม่ใช่ trading bot**

หน้าที่ของระบบมีแค่

1. วิเคราะห์โครงสร้างคลื่น
2. ตรวจสอบกฎ Elliott Wave
3. หา Key Price จาก Fibonacci
4. สร้าง Scenario

---

# Core Philosophy

Structure First

ระบบนี้โฟกัส

Elliott Wave Structure Engine

ไม่เพิ่ม indicator หรือระบบอื่นจนกว่าส่วนนี้จะนิ่ง

---

# System Responsibilities

ระบบต้องทำได้ 4 อย่างเท่านั้น

## 1 Wave Detection

ตรวจจับคลื่น

- Impulse
- ABC Correction
- Flat
- Expanded Flat
- Running Flat
- Triangle
- WXY
- Leading Diagonal
- Ending Diagonal

---

## 2 Rule Validation

ตรวจสอบกฎ Elliott Wave

- Wave2 cannot retrace beyond Wave1 origin
- Wave3 cannot be the shortest
- Wave4 cannot overlap Wave1

---

## 3 Key Price Detection

หา

- support
- resistance
- confirmation
- invalidation

โดยใช้

Fibonacci retracement  
Fibonacci extension

---

## 4 Scenario Generation

สร้าง

- Main Scenario
- Alternate Scenario

พร้อม

- targets
- stop level
- confirmation level
- invalidation level

---

# What This System Does NOT Do

เพื่อกันโปรเจกต์บานปลาย

ระบบนี้ **ไม่ทำ**

- auto trading
- order execution
- portfolio management
- telegram bot
- exchange integration

---

# Architecture

---

# System Flow

Price Data

→ Pivot Detection

→ Wave Detection

→ Rule Validation

→ Multi Count Engine

→ Probability Ranking

→ Key Level Extraction

→ Scenario Generation

---

# Backtesting

ระบบทดสอบด้วย

- BTC 1W
- BTC 1D
- BTC 4H

วัด

direction correctness

---

# Project Ceiling

โปรเจกต์นี้มีเพดาน

เมื่อครบสิ่งนี้ถือว่าเสร็จ

- wave detection
- rule validation
- fibonacci key levels
- scenario generation
- multi count ranking
- backtesting framework

หลังจากนี้ **หยุดพัฒนา**

---

# Final Goal

Deterministic Elliott Wave Analysis Engine

ที่

- วิเคราะห์โครงสร้างตลาด
- สร้าง scenario
- หา key price

โดยไม่พยายามทำนายตลาด 100%

# Data Requirements

ระบบต้องใช้ข้อมูล OHLCV

Required columns

- open_time
- open
- high
- low
- close
- volume

Supported timeframes

- 1W
- 1D
- 4H

Pivot detection จะสร้าง swing structure จากข้อมูลนี้

# Wave Detection Method

ระบบใช้

Fractal Pivot Detection

เพื่อสร้าง

market swing structure

pivot types

- H (swing high)
- L (swing low)

จากนั้นใช้ swing เหล่านี้สร้าง

- impulse
- correction patterns

# Multi Count System

ตลาดสามารถตีความคลื่นได้หลายแบบ

ระบบจะสร้าง

multiple wave counts

จากนั้นใช้

confidence scoring

เพื่อจัดอันดับ

- main count
- alternate count

# Deterministic Design

ระบบนี้เป็น deterministic system

หมายความว่า

given the same price data

the system must produce

the same wave interpretation

ทุกครั้ง

ไม่มี

- randomness
- machine learning
- probabilistic guessing

ผลลัพธ์ต้องมาจาก

- Elliott Wave rules
- Fibonacci relationships
- market structure