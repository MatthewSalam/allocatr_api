# 🏠 Allocatr

> **Smart Hostel Allocation & QR-Based Registration Clearance System for Nigerian Universities**

A production-ready FastAPI backend system that automates hostel room allocation using a First-Come-First-Served (FCFS) algorithm and streamlines multi-department clearance using HMAC-secured QR codes.

[![FastAPI](https://img.shields.io/badge/FastAPI-0.109.0-009688.svg?style=flat&logo=FastAPI)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg?style=flat&logo=python)](https://www.python.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Neon-4169E1.svg?style=flat&logo=postgresql)](https://neon.tech)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 🎯 Problem Statement

Nigerian universities face significant challenges in hostel allocation and student clearance:

1. **Manual Allocation Process**: Prone to errors, favoritism, and inefficiency
2. **Long Clearance Queues**: Students spend hours moving between 7+ departments for clearance stamps
3. **Lost Documentation**: Paper-based receipts and clearance forms get misplaced
4. **Lack of Transparency**: No real-time visibility into allocation status or clearance progress
5. **Corruption Vulnerabilities**: Manual processes create opportunities for manipulation

**Allocatr** addresses these challenges through automation, transparency, and digital verification.

---

## ✨ Solution

**Allocatr** is a two-module system:

### **Module 1: Hostel Allocation**
- Students upload payment receipts
- Admins verify receipts
- **FCFS Algorithm** allocates rooms based on upload timestamp (fairness guaranteed)
- Room preferences honored when available
- Gender-separated allocation
- Real-time occupancy tracking

### **Module 2: QR-Based Clearance**
- Auto-generated QR codes for allocated students
- **HMAC-SHA256 signature** prevents forgery
- Officers scan QR codes at their departments
- Real-time progress tracking (X/7 departments cleared)
- Downloadable QR codes (PNG/PDF)

---

## 🚀 Key Features

### **For Students**
- ✅ Online receipt upload
- ✅ View allocation status
- ✅ Download QR code (PNG/PDF)
- ✅ Track clearance progress (3/7 departments cleared = 43%)
- ✅ Room preference system

### **For Admins**
- ✅ Verify/reject receipts
- ✅ Trigger FCFS allocation
- ✅ View system statistics
- ✅ Manage rooms (CRUD operations)
- ✅ Monitor allocations

### **For Officers**
- ✅ Scan QR codes via mobile
- ✅ Record departmental clearance
- ✅ View department-specific clearances
- ✅ Role-based access (officer can only clear for their department)

### **System-Wide**
- ✅ Dual authentication (Bearer token + OAuth2)
- ✅ Role-based access control (Student | Admin | Officer)
- ✅ Audit logging
- ✅ RESTful API design
- ✅ Comprehensive error handling

---

## 🛠 Tech Stack

### **Backend**
- **Framework**: FastAPI (Python 3.11+)
- **Database**: PostgreSQL (Neon for production) / SQLite (development)
- **ORM**: SQLAlchemy
- **Authentication**: JWT (Jose) + Bcrypt
- **QR Generation**: python-qrcode with Pillow
- **Security**: HMAC-SHA256 for QR signatures
- **API Documentation**: Swagger UI (auto-generated)

### **DevOps**
- **Deployment**: Render / Railway (backend)
- **Database**: Neon (serverless PostgreSQL)
- **Version Control**: Git & GitHub
- **Environment Management**: python-dotenv

---

## 🏗 Architecture

### **System Architecture**
