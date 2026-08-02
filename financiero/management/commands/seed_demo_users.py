# -*- coding: utf-8 -*-
"""
Management command: seed_demo_users
Crea 10 usuarios demo realistas con registros mensuales y análisis ML.
Uso: python manage.py seed_demo_users
"""

from datetime import date
from django.core.management.base import BaseCommand
from django.db import transaction


USUARIOS_DATA = [
    {
        "email":          "maria.garcia@gmail.com",
        "nickname":       "MariaG",
        "password":       "SmartSave2024!",
        "edad":           28,
        "nivel_educ":     5,
        "miembros_hogar": 2,
        "ciudad":         "Lima",
        "registros": [
            {"periodo": date(2025, 1, 1), "ing_planilla": 1800, "ing_informal": 0,   "bonif": 0,    "alim": 480, "vest": 120, "viv": 480, "sal": 80,  "trans": 120, "com": 60,  "educ": 0,   "otros": 150},
            {"periodo": date(2025, 2, 1), "ing_planilla": 1800, "ing_informal": 0,   "bonif": 0,    "alim": 460, "vest": 200, "viv": 480, "sal": 50,  "trans": 120, "com": 60,  "educ": 0,   "otros": 300},
            {"periodo": date(2025, 3, 1), "ing_planilla": 1800, "ing_informal": 150, "bonif": 0,    "alim": 470, "vest": 80,  "viv": 480, "sal": 60,  "trans": 130, "com": 60,  "educ": 0,   "otros": 180},
            {"periodo": date(2025, 4, 1), "ing_planilla": 1800, "ing_informal": 0,   "bonif": 0,    "alim": 490, "vest": 90,  "viv": 480, "sal": 70,  "trans": 125, "com": 60,  "educ": 0,   "otros": 200},
            {"periodo": date(2025, 5, 1), "ing_planilla": 1900, "ing_informal": 0,   "bonif": 1900, "alim": 500, "vest": 350, "viv": 480, "sal": 90,  "trans": 130, "com": 60,  "educ": 0,   "otros": 400},
            {"periodo": date(2025, 6, 1), "ing_planilla": 1900, "ing_informal": 0,   "bonif": 0,    "alim": 480, "vest": 100, "viv": 490, "sal": 60,  "trans": 125, "com": 60,  "educ": 0,   "otros": 160},
        ],
        "analisis": [
            {"periodo": date(2025, 4, 1), "meta": 200},
            {"periodo": date(2025, 6, 1), "meta": 250, "elegir_plan": "Equilibrado"},
        ],
    },
    {
        "email":          "roberto.silva@hotmail.com",
        "nickname":       "RobertoS",
        "password":       "SmartSave2024!",
        "edad":           45,
        "nivel_educ":     4,
        "miembros_hogar": 4,
        "ciudad":         "Arequipa",
        "registros": [
            {"periodo": date(2025, 1, 1), "ing_planilla": 2200, "ing_informal": 600,  "bonif": 0,    "alim": 900, "vest": 200, "viv": 700, "sal": 150, "trans": 250, "com": 100, "educ": 300, "otros": 350},
            {"periodo": date(2025, 2, 1), "ing_planilla": 2200, "ing_informal": 400,  "bonif": 0,    "alim": 850, "vest": 150, "viv": 700, "sal": 200, "trans": 250, "com": 100, "educ": 300, "otros": 280},
            {"periodo": date(2025, 3, 1), "ing_planilla": 2200, "ing_informal": 800,  "bonif": 0,    "alim": 920, "vest": 100, "viv": 700, "sal": 180, "trans": 260, "com": 100, "educ": 300, "otros": 400},
            {"periodo": date(2025, 4, 1), "ing_planilla": 2200, "ing_informal": 300,  "bonif": 0,    "alim": 880, "vest": 80,  "viv": 700, "sal": 250, "trans": 250, "com": 100, "educ": 300, "otros": 200},
            {"periodo": date(2025, 5, 1), "ing_planilla": 2200, "ing_informal": 700,  "bonif": 2200, "alim": 950, "vest": 300, "viv": 700, "sal": 180, "trans": 270, "com": 100, "educ": 300, "otros": 500},
        ],
        "analisis": [
            {"periodo": date(2025, 3, 1), "meta": 300},
            {"periodo": date(2025, 5, 1), "meta": 400, "elegir_plan": "Suave"},
        ],
    },
    {
        "email":          "andrea.flores@gmail.com",
        "nickname":       "AndreaF",
        "password":       "SmartSave2024!",
        "edad":           23,
        "nivel_educ":     5,
        "miembros_hogar": 1,
        "ciudad":         "Lima",
        "registros": [
            {"periodo": date(2025, 2, 1), "ing_planilla": 1100, "ing_informal": 200, "bonif": 0,   "alim": 350, "vest": 180, "viv": 550, "sal": 40,  "trans": 100, "com": 80,  "educ": 250, "otros": 200},
            {"periodo": date(2025, 3, 1), "ing_planilla": 1100, "ing_informal": 150, "bonif": 0,   "alim": 360, "vest": 90,  "viv": 550, "sal": 30,  "trans": 100, "com": 80,  "educ": 250, "otros": 180},
            {"periodo": date(2025, 4, 1), "ing_planilla": 1100, "ing_informal": 250, "bonif": 0,   "alim": 340, "vest": 60,  "viv": 550, "sal": 50,  "trans": 100, "com": 80,  "educ": 250, "otros": 150},
            {"periodo": date(2025, 5, 1), "ing_planilla": 1200, "ing_informal": 100, "bonif": 0,   "alim": 370, "vest": 120, "viv": 550, "sal": 40,  "trans": 110, "com": 80,  "educ": 250, "otros": 220},
            {"periodo": date(2025, 6, 1), "ing_planilla": 1200, "ing_informal": 300, "bonif": 0,   "alim": 355, "vest": 70,  "viv": 550, "sal": 35,  "trans": 110, "com": 80,  "educ": 250, "otros": 160},
        ],
        "analisis": [
            {"periodo": date(2025, 4, 1), "meta": 100},
            {"periodo": date(2025, 6, 1), "meta": 150, "elegir_plan": "Suave"},
        ],
    },
    {
        "email":          "jorge.mamani@yahoo.com",
        "nickname":       "JorgeM",
        "password":       "SmartSave2024!",
        "edad":           38,
        "nivel_educ":     4,
        "miembros_hogar": 3,
        "ciudad":         "Cusco",
        "registros": [
            {"periodo": date(2025, 1, 1), "ing_planilla": 0,    "ing_informal": 1800, "bonif": 0,   "alim": 600, "vest": 150, "viv": 500, "sal": 80,  "trans": 200, "com": 80,  "educ": 200, "otros": 280},
            {"periodo": date(2025, 2, 1), "ing_planilla": 0,    "ing_informal": 2200, "bonif": 0,   "alim": 620, "vest": 100, "viv": 500, "sal": 70,  "trans": 220, "com": 80,  "educ": 200, "otros": 300},
            {"periodo": date(2025, 3, 1), "ing_planilla": 0,    "ing_informal": 2800, "bonif": 0,   "alim": 650, "vest": 80,  "viv": 500, "sal": 90,  "trans": 240, "com": 80,  "educ": 200, "otros": 350},
            {"periodo": date(2025, 4, 1), "ing_planilla": 0,    "ing_informal": 3200, "bonif": 0,   "alim": 680, "vest": 120, "viv": 500, "sal": 100, "trans": 260, "com": 80,  "educ": 200, "otros": 400},
            {"periodo": date(2025, 5, 1), "ing_planilla": 0,    "ing_informal": 1200, "bonif": 0,   "alim": 580, "vest": 200, "viv": 500, "sal": 120, "trans": 180, "com": 80,  "educ": 200, "otros": 350},
            {"periodo": date(2025, 6, 1), "ing_planilla": 0,    "ing_informal": 1000, "bonif": 0,   "alim": 560, "vest": 80,  "viv": 500, "sal": 80,  "trans": 160, "com": 80,  "educ": 200, "otros": 200},
        ],
        "analisis": [
            {"periodo": date(2025, 3, 1), "meta": 400},
            {"periodo": date(2025, 6, 1), "meta": 150},
        ],
    },
    {
        "email":          "patricia.ruiz@gmail.com",
        "nickname":       "PatriciaR",
        "password":       "SmartSave2024!",
        "edad":           52,
        "nivel_educ":     6,
        "miembros_hogar": 2,
        "ciudad":         "Lima",
        "registros": [
            {"periodo": date(2025, 1, 1), "ing_planilla": 4500, "ing_informal": 0,   "bonif": 0,    "alim": 700, "vest": 200, "viv": 900, "sal": 350, "trans": 200, "com": 80,  "educ": 0,   "otros": 300},
            {"periodo": date(2025, 2, 1), "ing_planilla": 4500, "ing_informal": 0,   "bonif": 0,    "alim": 680, "vest": 150, "viv": 900, "sal": 300, "trans": 200, "com": 80,  "educ": 0,   "otros": 250},
            {"periodo": date(2025, 3, 1), "ing_planilla": 4500, "ing_informal": 500, "bonif": 0,    "alim": 720, "vest": 180, "viv": 900, "sal": 280, "trans": 210, "com": 80,  "educ": 400, "otros": 320},
            {"periodo": date(2025, 4, 1), "ing_planilla": 4500, "ing_informal": 0,   "bonif": 0,    "alim": 710, "vest": 160, "viv": 900, "sal": 320, "trans": 205, "com": 80,  "educ": 0,   "otros": 280},
            {"periodo": date(2025, 5, 1), "ing_planilla": 4500, "ing_informal": 0,   "bonif": 4500, "alim": 750, "vest": 400, "viv": 900, "sal": 400, "trans": 220, "com": 80,  "educ": 0,   "otros": 500},
            {"periodo": date(2025, 6, 1), "ing_planilla": 4500, "ing_informal": 0,   "bonif": 0,    "alim": 700, "vest": 150, "viv": 900, "sal": 340, "trans": 200, "com": 80,  "educ": 0,   "otros": 270},
        ],
        "analisis": [
            {"periodo": date(2025, 4, 1), "meta": 1500},
            {"periodo": date(2025, 6, 1), "meta": 1500, "elegir_plan": "Equilibrado"},
        ],
    },
    {
        "email":          "diego.torres@gmail.com",
        "nickname":       "DiegoT",
        "password":       "SmartSave2024!",
        "edad":           31,
        "nivel_educ":     5,
        "miembros_hogar": 1,
        "ciudad":         "Trujillo",
        "registros": [
            {"periodo": date(2025, 1, 1), "ing_planilla": 5500, "ing_informal": 800,  "bonif": 0,    "alim": 500, "vest": 250, "viv": 1200, "sal": 100, "trans": 150, "com": 120, "educ": 500, "otros": 600},
            {"periodo": date(2025, 2, 1), "ing_planilla": 5500, "ing_informal": 600,  "bonif": 0,    "alim": 480, "vest": 200, "viv": 1200, "sal": 80,  "trans": 150, "com": 120, "educ": 500, "otros": 450},
            {"periodo": date(2025, 3, 1), "ing_planilla": 5500, "ing_informal": 1200, "bonif": 0,    "alim": 520, "vest": 300, "viv": 1200, "sal": 120, "trans": 160, "com": 120, "educ": 500, "otros": 700},
            {"periodo": date(2025, 4, 1), "ing_planilla": 5500, "ing_informal": 1000, "bonif": 0,    "alim": 510, "vest": 180, "viv": 1200, "sal": 100, "trans": 155, "com": 120, "educ": 500, "otros": 550},
            {"periodo": date(2025, 5, 1), "ing_planilla": 6000, "ing_informal": 900,  "bonif": 6000, "alim": 550, "vest": 500, "viv": 1200, "sal": 150, "trans": 160, "com": 120, "educ": 500, "otros": 900},
        ],
        "analisis": [
            {"periodo": date(2025, 2, 1), "meta": 2500},
            {"periodo": date(2025, 4, 1), "meta": 2500, "elegir_plan": "Decidido"},
        ],
    },
    {
        "email":          "carmen.quispe@outlook.com",
        "nickname":       "CarmenQ",
        "password":       "SmartSave2024!",
        "edad":           44,
        "nivel_educ":     3,
        "miembros_hogar": 5,
        "ciudad":         "Puno",
        "registros": [
            {"periodo": date(2025, 1, 1), "ing_planilla": 0,    "ing_informal": 1500, "bonif": 0,   "alim": 800, "vest": 300, "viv": 400, "sal": 200, "trans": 150, "com": 80,  "educ": 300, "otros": 250},
            {"periodo": date(2025, 2, 1), "ing_planilla": 0,    "ing_informal": 1300, "bonif": 0,   "alim": 820, "vest": 200, "viv": 400, "sal": 150, "trans": 140, "com": 80,  "educ": 300, "otros": 200},
            {"periodo": date(2025, 3, 1), "ing_planilla": 0,    "ing_informal": 1700, "bonif": 0,   "alim": 850, "vest": 180, "viv": 400, "sal": 180, "trans": 160, "com": 80,  "educ": 300, "otros": 350},
            {"periodo": date(2025, 4, 1), "ing_planilla": 0,    "ing_informal": 1100, "bonif": 0,   "alim": 810, "vest": 250, "viv": 400, "sal": 220, "trans": 130, "com": 80,  "educ": 300, "otros": 300},
            {"periodo": date(2025, 5, 1), "ing_planilla": 0,    "ing_informal": 2000, "bonif": 0,   "alim": 880, "vest": 150, "viv": 400, "sal": 170, "trans": 170, "com": 80,  "educ": 300, "otros": 280},
        ],
        "analisis": [
            {"periodo": date(2025, 3, 1), "meta": 200},
            {"periodo": date(2025, 5, 1), "meta": 250, "elegir_plan": "Suave"},
        ],
    },
    {
        "email":          "luis.medina@gmail.com",
        "nickname":       "LuisM",
        "password":       "SmartSave2024!",
        "edad":           29,
        "nivel_educ":     4,
        "miembros_hogar": 2,
        "ciudad":         "Lima",
        "registros": [
            {"periodo": date(2025, 1, 1), "ing_planilla": 3200, "ing_informal": 0,   "bonif": 0,    "alim": 600, "vest": 150, "viv": 900, "sal": 80,  "trans": 450, "com": 80,  "educ": 0,   "otros": 350},
            {"periodo": date(2025, 2, 1), "ing_planilla": 3200, "ing_informal": 0,   "bonif": 0,    "alim": 580, "vest": 100, "viv": 900, "sal": 100, "trans": 430, "com": 80,  "educ": 0,   "otros": 280},
            {"periodo": date(2025, 3, 1), "ing_planilla": 3200, "ing_informal": 200, "bonif": 0,    "alim": 620, "vest": 80,  "viv": 900, "sal": 90,  "trans": 460, "com": 80,  "educ": 0,   "otros": 300},
            {"periodo": date(2025, 4, 1), "ing_planilla": 3200, "ing_informal": 0,   "bonif": 0,    "alim": 590, "vest": 120, "viv": 900, "sal": 110, "trans": 440, "com": 80,  "educ": 200, "otros": 320},
            {"periodo": date(2025, 5, 1), "ing_planilla": 3500, "ing_informal": 0,   "bonif": 3500, "alim": 650, "vest": 250, "viv": 900, "sal": 150, "trans": 470, "com": 80,  "educ": 0,   "otros": 450},
            {"periodo": date(2025, 6, 1), "ing_planilla": 3500, "ing_informal": 0,   "bonif": 0,    "alim": 600, "vest": 100, "viv": 900, "sal": 100, "trans": 450, "com": 80,  "educ": 0,   "otros": 260},
        ],
        "analisis": [
            {"periodo": date(2025, 3, 1), "meta": 400},
            {"periodo": date(2025, 6, 1), "meta": 500, "elegir_plan": "Equilibrado"},
        ],
    },
    {
        "email":          "sofia.vargas@gmail.com",
        "nickname":       "SofiaV",
        "password":       "SmartSave2024!",
        "edad":           35,
        "nivel_educ":     5,
        "miembros_hogar": 3,
        "ciudad":         "Piura",
        "registros": [
            {"periodo": date(2025, 1, 1), "ing_planilla": 3800, "ing_informal": 0,   "bonif": 0,    "alim": 700, "vest": 150, "viv": 800, "sal": 120, "trans": 200, "com": 80,  "educ": 400, "otros": 250},
            {"periodo": date(2025, 2, 1), "ing_planilla": 3800, "ing_informal": 0,   "bonif": 0,    "alim": 680, "vest": 100, "viv": 800, "sal": 100, "trans": 200, "com": 80,  "educ": 400, "otros": 200},
            {"periodo": date(2025, 3, 1), "ing_planilla": 3800, "ing_informal": 200, "bonif": 0,    "alim": 720, "vest": 130, "viv": 800, "sal": 150, "trans": 210, "com": 80,  "educ": 400, "otros": 280},
            {"periodo": date(2025, 4, 1), "ing_planilla": 3800, "ing_informal": 0,   "bonif": 0,    "alim": 690, "vest": 120, "viv": 800, "sal": 130, "trans": 205, "com": 80,  "educ": 400, "otros": 230},
            {"periodo": date(2025, 5, 1), "ing_planilla": 3800, "ing_informal": 0,   "bonif": 3800, "alim": 750, "vest": 300, "viv": 800, "sal": 180, "trans": 220, "com": 80,  "educ": 400, "otros": 400},
            {"periodo": date(2025, 6, 1), "ing_planilla": 3800, "ing_informal": 300, "bonif": 0,    "alim": 700, "vest": 110, "viv": 800, "sal": 125, "trans": 200, "com": 80,  "educ": 400, "otros": 210},
        ],
        "analisis": [
            {"periodo": date(2025, 4, 1), "meta": 800},
            {"periodo": date(2025, 6, 1), "meta": 900, "elegir_plan": "Equilibrado"},
        ],
    },
    {
        "email":          "miguel.castro@gmail.com",
        "nickname":       "MiguelC",
        "password":       "SmartSave2024!",
        "edad":           26,
        "nivel_educ":     4,
        "miembros_hogar": 1,
        "ciudad":         "Lima",
        "registros": [
            {"periodo": date(2025, 2, 1), "ing_planilla": 0,    "ing_informal": 1400, "bonif": 0,   "alim": 420, "vest": 150, "viv": 600, "sal": 50,  "trans": 500, "com": 80,  "educ": 0,   "otros": 200},
            {"periodo": date(2025, 3, 1), "ing_planilla": 0,    "ing_informal": 1600, "bonif": 0,   "alim": 430, "vest": 80,  "viv": 600, "sal": 40,  "trans": 520, "com": 80,  "educ": 0,   "otros": 180},
            {"periodo": date(2025, 4, 1), "ing_planilla": 0,    "ing_informal": 1200, "bonif": 0,   "alim": 410, "vest": 100, "viv": 600, "sal": 60,  "trans": 490, "com": 80,  "educ": 0,   "otros": 220},
            {"periodo": date(2025, 5, 1), "ing_planilla": 0,    "ing_informal": 1800, "bonif": 0,   "alim": 440, "vest": 60,  "viv": 600, "sal": 45,  "trans": 540, "com": 80,  "educ": 0,   "otros": 150},
            {"periodo": date(2025, 6, 1), "ing_planilla": 0,    "ing_informal": 1350, "bonif": 0,   "alim": 425, "vest": 120, "viv": 600, "sal": 55,  "trans": 510, "com": 80,  "educ": 0,   "otros": 250},
        ],
        "analisis": [
            {"periodo": date(2025, 4, 1), "meta": 100},
            {"periodo": date(2025, 6, 1), "meta": 120, "elegir_plan": "Suave"},
        ],
    },
    # ── Lote 2: 5 usuarios adicionales ───────────────────────────────────────
    {
        "email":          "valeria.mendoza@gmail.com",
        "nickname":       "ValeriaM",
        "password":       "SmartSave2024!",
        "edad":           27,
        "nivel_educ":     5,
        "miembros_hogar": 1,
        "ciudad":         "Lima",
        "registros": [
            {"periodo": date(2025, 1, 1), "ing_planilla": 0,    "ing_informal": 1600, "bonif": 0,   "alim": 380, "vest": 280, "viv": 700, "sal": 40,  "trans": 90,  "com": 100, "educ": 0,   "otros": 450},
            {"periodo": date(2025, 2, 1), "ing_planilla": 0,    "ing_informal": 1900, "bonif": 0,   "alim": 360, "vest": 350, "viv": 700, "sal": 30,  "trans": 90,  "com": 100, "educ": 0,   "otros": 600},
            {"periodo": date(2025, 3, 1), "ing_planilla": 0,    "ing_informal": 1400, "bonif": 0,   "alim": 370, "vest": 200, "viv": 700, "sal": 50,  "trans": 90,  "com": 100, "educ": 0,   "otros": 380},
            {"periodo": date(2025, 4, 1), "ing_planilla": 0,    "ing_informal": 2100, "bonif": 0,   "alim": 400, "vest": 180, "viv": 700, "sal": 35,  "trans": 95,  "com": 100, "educ": 0,   "otros": 420},
            {"periodo": date(2025, 5, 1), "ing_planilla": 0,    "ing_informal": 1750, "bonif": 0,   "alim": 390, "vest": 300, "viv": 700, "sal": 45,  "trans": 90,  "com": 100, "educ": 0,   "otros": 500},
            {"periodo": date(2025, 6, 1), "ing_planilla": 0,    "ing_informal": 2000, "bonif": 0,   "alim": 375, "vest": 220, "viv": 700, "sal": 40,  "trans": 90,  "com": 100, "educ": 0,   "otros": 350},
        ],
        "analisis": [
            {"periodo": date(2025, 3, 1), "meta": 150},
            {"periodo": date(2025, 6, 1), "meta": 200, "elegir_plan": "Equilibrado"},
        ],
    },
    {
        "email":          "fernando.chavez@gmail.com",
        "nickname":       "FernandoC",
        "password":       "SmartSave2024!",
        "edad":           55,
        "nivel_educ":     4,
        "miembros_hogar": 5,
        "ciudad":         "Lima",
        "registros": [
            {"periodo": date(2025, 1, 1), "ing_planilla": 1500, "ing_informal": 1000, "bonif": 0,   "alim": 950, "vest": 200, "viv": 750, "sal": 250, "trans": 200, "com": 100, "educ": 350, "otros": 300},
            {"periodo": date(2025, 2, 1), "ing_planilla": 1500, "ing_informal": 800,  "bonif": 0,   "alim": 900, "vest": 150, "viv": 750, "sal": 300, "trans": 190, "com": 100, "educ": 350, "otros": 250},
            {"periodo": date(2025, 3, 1), "ing_planilla": 1500, "ing_informal": 1300, "bonif": 0,   "alim": 980, "vest": 100, "viv": 750, "sal": 200, "trans": 210, "com": 100, "educ": 350, "otros": 350},
            {"periodo": date(2025, 4, 1), "ing_planilla": 1500, "ing_informal": 600,  "bonif": 0,   "alim": 920, "vest": 80,  "viv": 750, "sal": 350, "trans": 200, "com": 100, "educ": 350, "otros": 200},
            {"periodo": date(2025, 5, 1), "ing_planilla": 1500, "ing_informal": 1500, "bonif": 1500,"alim": 1000,"vest": 300, "viv": 750, "sal": 280, "trans": 220, "com": 100, "educ": 350, "otros": 400},
            {"periodo": date(2025, 6, 1), "ing_planilla": 1500, "ing_informal": 900,  "bonif": 0,   "alim": 940, "vest": 120, "viv": 750, "sal": 260, "trans": 200, "com": 100, "educ": 350, "otros": 280},
        ],
        "analisis": [
            {"periodo": date(2025, 2, 1), "meta": 200},
            {"periodo": date(2025, 6, 1), "meta": 250, "elegir_plan": "Suave"},
        ],
    },
    {
        "email":          "daniela.rios@gmail.com",
        "nickname":       "DanielaR",
        "password":       "SmartSave2024!",
        "edad":           32,
        "nivel_educ":     5,
        "miembros_hogar": 2,
        "ciudad":         "Ica",
        "registros": [
            {"periodo": date(2025, 1, 1), "ing_planilla": 3000, "ing_informal": 400,  "bonif": 0,   "alim": 550, "vest": 120, "viv": 700, "sal": 100, "trans": 160, "com": 80,  "educ": 200, "otros": 280},
            {"periodo": date(2025, 2, 1), "ing_planilla": 3000, "ing_informal": 300,  "bonif": 0,   "alim": 530, "vest": 90,  "viv": 700, "sal": 80,  "trans": 155, "com": 80,  "educ": 200, "otros": 220},
            {"periodo": date(2025, 3, 1), "ing_planilla": 3000, "ing_informal": 600,  "bonif": 0,   "alim": 570, "vest": 140, "viv": 700, "sal": 120, "trans": 165, "com": 80,  "educ": 200, "otros": 300},
            {"periodo": date(2025, 4, 1), "ing_planilla": 3000, "ing_informal": 500,  "bonif": 0,   "alim": 545, "vest": 100, "viv": 700, "sal": 110, "trans": 160, "com": 80,  "educ": 200, "otros": 250},
            {"periodo": date(2025, 5, 1), "ing_planilla": 3000, "ing_informal": 400,  "bonif": 3000,"alim": 600, "vest": 280, "viv": 700, "sal": 160, "trans": 170, "com": 80,  "educ": 200, "otros": 380},
        ],
        "analisis": [
            {"periodo": date(2025, 3, 1), "meta": 700},
            {"periodo": date(2025, 5, 1), "meta": 800, "elegir_plan": "Decidido"},
        ],
    },
    {
        "email":          "angel.paredes@outlook.com",
        "nickname":       "AngelP",
        "password":       "SmartSave2024!",
        "edad":           40,
        "nivel_educ":     3,
        "miembros_hogar": 4,
        "ciudad":         "Huancayo",
        "registros": [
            {"periodo": date(2025, 1, 1), "ing_planilla": 0,    "ing_informal": 2400, "bonif": 0,   "alim": 800, "vest": 180, "viv": 550, "sal": 150, "trans": 700, "com": 80,  "educ": 250, "otros": 300},
            {"periodo": date(2025, 2, 1), "ing_planilla": 0,    "ing_informal": 2000, "bonif": 0,   "alim": 780, "vest": 120, "viv": 550, "sal": 180, "trans": 680, "com": 80,  "educ": 250, "otros": 250},
            {"periodo": date(2025, 3, 1), "ing_planilla": 0,    "ing_informal": 2800, "bonif": 0,   "alim": 850, "vest": 100, "viv": 550, "sal": 140, "trans": 720, "com": 80,  "educ": 250, "otros": 350},
            {"periodo": date(2025, 4, 1), "ing_planilla": 0,    "ing_informal": 1800, "bonif": 0,   "alim": 760, "vest": 150, "viv": 550, "sal": 200, "trans": 650, "com": 80,  "educ": 250, "otros": 280},
            {"periodo": date(2025, 5, 1), "ing_planilla": 0,    "ing_informal": 3000, "bonif": 0,   "alim": 900, "vest": 80,  "viv": 550, "sal": 130, "trans": 750, "com": 80,  "educ": 250, "otros": 200},
            {"periodo": date(2025, 6, 1), "ing_planilla": 0,    "ing_informal": 2200, "bonif": 0,   "alim": 820, "vest": 100, "viv": 550, "sal": 160, "trans": 700, "com": 80,  "educ": 250, "otros": 320},
        ],
        "analisis": [
            {"periodo": date(2025, 3, 1), "meta": 300},
            {"periodo": date(2025, 6, 1), "meta": 250, "elegir_plan": "Suave"},
        ],
    },
    {
        "email":          "camila.espinoza@gmail.com",
        "nickname":       "CamilaE",
        "password":       "SmartSave2024!",
        "edad":           22,
        "nivel_educ":     5,
        "miembros_hogar": 1,
        "ciudad":         "Lima",
        "registros": [
            {"periodo": date(2025, 3, 1), "ing_planilla": 1300, "ing_informal": 0,   "bonif": 0,   "alim": 320, "vest": 150, "viv": 600, "sal": 30,  "trans": 90,  "com": 70,  "educ": 100, "otros": 180},
            {"periodo": date(2025, 4, 1), "ing_planilla": 1300, "ing_informal": 0,   "bonif": 0,   "alim": 310, "vest": 80,  "viv": 600, "sal": 25,  "trans": 90,  "com": 70,  "educ": 100, "otros": 150},
            {"periodo": date(2025, 5, 1), "ing_planilla": 1300, "ing_informal": 200, "bonif": 0,   "alim": 330, "vest": 60,  "viv": 600, "sal": 30,  "trans": 90,  "com": 70,  "educ": 100, "otros": 130},
            {"periodo": date(2025, 6, 1), "ing_planilla": 1400, "ing_informal": 0,   "bonif": 0,   "alim": 320, "vest": 100, "viv": 600, "sal": 28,  "trans": 90,  "com": 70,  "educ": 100, "otros": 160},
        ],
        "analisis": [
            {"periodo": date(2025, 4, 1), "meta": 80},
            {"periodo": date(2025, 6, 1), "meta": 100, "elegir_plan": "Equilibrado"},
        ],
    },
]


class Command(BaseCommand):
    help = "Crea 10 usuarios demo con registros mensuales y análisis ML en la BD activa."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Omite usuarios que ya existen (no lanza error).",
        )

    def handle(self, *args, **options):
        from accounts.models import Rol, Usuario
        from financiero.models import RegistroMensual
        from recomendaciones.models import MetaMensual, PlanSeleccionado, ResultadoML
        from src.predict import classify, recommend, shap_explain
        from recomendaciones.trends import historial_user_dicts

        rol_usuario, _ = Rol.objects.get_or_create(
            nombre=Rol.USUARIO,
            defaults={"descripcion": "Usuario estándar del sistema"},
        )

        creados = 0
        omitidos = 0

        for data in USUARIOS_DATA:
            email = data["email"]

            if Usuario.objects.filter(email=email).exists():
                if options["force"]:
                    self.stdout.write(f"  SKIP: {email} ya existe")
                    omitidos += 1
                    continue
                else:
                    self.stdout.write(self.style.WARNING(f"  WARN: {email} ya existe (usa --force para omitir)"))
                    omitidos += 1
                    continue

            with transaction.atomic():
                # ── 1. Crear usuario ──────────────────────────────────────────
                user = Usuario.objects.create_user(
                    email=email,
                    username=data["nickname"],
                    nickname=data["nickname"],
                    password=data["password"],
                    edad=data["edad"],
                    nivel_educ=data["nivel_educ"],
                    miembros_hogar=data["miembros_hogar"],
                    ciudad=data["ciudad"],
                    rol=rol_usuario,
                )
                self.stdout.write(f"\n[OK] Creado: {email} ({data['nickname']})")

                # ── 2. Crear registros mensuales ──────────────────────────────
                registros_por_periodo = {}
                for r in data["registros"]:
                    reg = RegistroMensual.objects.create(
                        usuario=user,
                        periodo=r["periodo"],
                        ing_planilla=r["ing_planilla"],
                        ing_informal=r["ing_informal"],
                        bonif_monto=r["bonif"],
                        gasto_alimentos=r["alim"],
                        gasto_vestido=r["vest"],
                        gasto_vivienda_servicios=r["viv"],
                        gasto_salud=r["sal"],
                        gasto_transporte=r["trans"],
                        gasto_comunicaciones=r["com"],
                        gasto_educacion=r["educ"],
                        gasto_otros_bienes=r["otros"],
                    )
                    registros_por_periodo[r["periodo"]] = reg
                    ahorro = reg.ahorro_bruto
                    signo = "+" if ahorro >= 0 else ""
                    self.stdout.write(f"   Registro {r['periodo'].strftime('%b %Y')} -> ahorro {signo}{ahorro:.0f} S/")

                # ── 3. Análisis ML ────────────────────────────────────────────
                historial = historial_user_dicts(user)
                for a in data["analisis"]:
                    periodo = a["periodo"]
                    meta_monto = a["meta"]
                    elegir = a.get("elegir_plan")

                    reg = registros_por_periodo.get(periodo)
                    if not reg:
                        self.stdout.write(self.style.WARNING(f"   WARN: Registro {periodo} no encontrado"))
                        continue

                    user_dict = reg.to_user_dict()

                    # ML
                    resultado_raw = recommend(user_dict, meta_monto, historial=historial)
                    cls = classify(user_dict)
                    shap_data = shap_explain(user_dict, top=3)
                    resultado_raw["clase_actual"] = cls
                    resultado_raw["diagnostico_shap"] = shap_data

                    # MetaMensual
                    meta_obj, _ = MetaMensual.objects.update_or_create(
                        usuario=user,
                        periodo=date(periodo.year, periodo.month, 1),
                        defaults={"monto": meta_monto},
                    )

                    # ResultadoML
                    resultado = ResultadoML.objects.create(
                        usuario=user,
                        registro=reg,
                        mes_referencia=reg,
                        meta=meta_obj,
                        ahorro_actual=resultado_raw["ahorro_actual"],
                        meta_validada=meta_monto,
                        necesita_recortar=resultado_raw["necesita_recortar"],
                        clase_predicha=cls["clase"],
                        label_predicha=cls["label"],
                        prob_ahorra=cls["probabilidad_ahorra"],
                        confianza=cls["confianza"],
                        shap_top_features=shap_data,
                    )

                    label = cls["label"]
                    prob = round(cls["probabilidad_ahorra"] * 100, 1)
                    falta = resultado_raw["necesita_recortar"]
                    self.stdout.write(
                        f"   ML {periodo.strftime('%b %Y')} -> {label} ({prob}%) "
                        f"| meta S/{meta_monto} | falta recortar S/{falta:.0f}"
                    )

                    # PlanSeleccionado
                    if elegir and resultado_raw.get("opciones"):
                        plan_data = next(
                            (o for o in resultado_raw["opciones"] if o["nombre"] == elegir),
                            None,
                        )
                        if plan_data:
                            PlanSeleccionado.objects.filter(usuario=user, activo=True).update(activo=False)
                            PlanSeleccionado.objects.create(
                                usuario=user,
                                resultado=resultado,
                                nombre_plan=elegir,
                                ahorro_proyectado=plan_data["ahorro_resultante"],
                                meta_ahorro=meta_monto,
                                gastos_sugeridos=plan_data.get("gastos_optimizados", {}),
                                activo=True,
                            )
                            self.stdout.write(f"   Plan {elegir} elegido")

                creados += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nSeed completado: {creados} usuarios creados, {omitidos} omitidos."
            )
        )
